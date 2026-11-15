"""Column-mapping wizard: own contract inventories → register."""

from __future__ import annotations

import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dora_roi.inventory import (
    FIELDS,
    FIELDS_BY_KEY,
    EntityInfo,
    build_raw,
    preview,
    read_inventory,
    suggest_mapping,
)
from dora_roi.lei import is_valid_lei
from dora_roi.model import EntityType
from dora_roi.model.refdata import COUNTRIES, CURRENCIES
from dora_roi.web.auth import current_owner
from dora_roi.web.context import (
    INVENTORY_SUFFIXES,
    Ctx,
    Wizard,
)
from dora_roi.web.i18n import translator
from dora_roi.workspace import Workspace

router = APIRouter()


@router.get("/map", response_class=HTMLResponse)
def wizard_start(ctx: Ctx, request: Request) -> HTMLResponse:
    return ctx.render(request, "wizard_upload.html.j2", wstep=1)

@router.post("/map")
async def wizard_upload(ctx: Ctx, request: Request,
                        file: Annotated[UploadFile | None, File()] = None,
                        use_sample: Annotated[str | None, Form()] = None) -> Response:
    with tempfile.TemporaryDirectory() as tmp:
        if use_sample:
            from dora_roi.sample.inventory_sample import write_sample_inventory

            path = write_sample_inventory(Path(tmp) / "Vertragsinventar.xlsx")
            name = path.name
        else:
            if file is None or not file.filename:
                return ctx.render(request, "wizard_upload.html.j2", status=400, wstep=1,
                              error=translator(ctx.lang_of(request))("wiz.error.required"))
            got = await ctx.read_upload(file, INVENTORY_SUFFIXES)
            if isinstance(got, str):
                return ctx.upload_error(request, got, "wizard_upload.html.j2", wstep=1)
            name, data = got
            # never use the client-supplied name as a path (T5 in docs/SECURITY.md)
            path = Path(tmp) / f"inventory{Path(name).suffix.lower()}"
            path.write_bytes(data)
        try:
            sheet = await ctx.offload(lambda: read_inventory(path))
        except Exception as exc:  # spreadsheet/csv readers raise many types on corrupt input
            t = translator(ctx.lang_of(request))
            return ctx.render(request, "wizard_upload.html.j2", status=400, wstep=1,
                          error=t("err.read", name=name, error=str(exc) or
                                  type(exc).__name__))
    sheet.source = name
    wiz = Wizard(uuid.uuid4().hex, sheet,
                 {s.column: s.field for s in suggest_mapping(sheet) if s.field})
    wiz.owner = current_owner()
    ctx.wizards.add(wiz.id, wiz)
    return RedirectResponse(f"/map/{wiz.id}", status_code=303)

@router.get("/map/{wid}", response_class=HTMLResponse)
def wizard_map(ctx: Ctx, request: Request, wid: str) -> HTMLResponse:
    wiz = ctx.wiz_or_404(wid)
    suggestions = {s.column: s for s in suggest_mapping(wiz.sheet)}
    return ctx.render(request, "wizard_map.html.j2", wstep=2, wiz=wiz, fields=FIELDS,
                  suggestions=suggestions)

@router.post("/map/{wid}")
async def wizard_map_save(ctx: Ctx, request: Request, wid: str) -> Response:
    wiz = ctx.wiz_or_404(wid)
    form = await request.form()
    mapping: dict[int, str] = {}
    for i in range(len(wiz.sheet.headers)):
        value = str(form.get(f"col{i}", "") or "")
        if value in FIELDS_BY_KEY and value not in mapping.values():
            mapping[i] = value
    wiz.mapping = mapping
    return RedirectResponse(f"/map/{wid}/entity", status_code=303)

def entity_defaults(wiz: Wizard) -> EntityInfo:
    return wiz.entity or EntityInfo(lei="", name="", country="DE",
                                    reporting_date=date(date.today().year - 1, 12, 31))

@router.get("/map/{wid}/entity", response_class=HTMLResponse)
def wizard_entity(ctx: Ctx, request: Request, wid: str) -> HTMLResponse:
    wiz = ctx.wiz_or_404(wid)
    return ctx.render(request, "wizard_entity.html.j2", wstep=3, wiz=wiz,
                  entity=entity_defaults(wiz), errors={}, entity_types=list(EntityType),
                  countries=COUNTRIES, currencies=sorted(CURRENCIES))

@router.post("/map/{wid}/entity")
async def wizard_entity_save(ctx: Ctx, request: Request, wid: str) -> Response:
    wiz = ctx.wiz_or_404(wid)
    form = await request.form()
    t = translator(ctx.lang_of(request))

    def field(name: str) -> str:
        return str(form.get(name, "") or "").strip()

    errors: dict[str, str] = {}
    lei = field("lei").upper()
    if not is_valid_lei(lei):
        errors["lei"] = t("wiz.error.lei")
    for name in ("name", "country"):
        if not field(name):
            errors[name] = t("wiz.error.required")
    try:
        ref = date.fromisoformat(field("reporting_date"))
    except ValueError:
        errors["reporting_date"] = t("wiz.error.required")
        ref = date(date.today().year - 1, 12, 31)
    entity = EntityInfo(lei=lei, name=field("name"), country=field("country").upper(),
                        entity_type=field("entity_type") or EntityType.CREDIT_INSTITUTION,
                        competent_authority=field("competent_authority"),
                        reporting_date=ref, currency=field("currency").upper() or "EUR")
    wiz.entity = entity
    if errors:
        return ctx.render(request, "wizard_entity.html.j2", status=400, wstep=3, wiz=wiz,
                      entity=entity, errors=errors, entity_types=list(EntityType),
                      countries=COUNTRIES, currencies=sorted(CURRENCIES))
    return RedirectResponse(f"/map/{wid}/preview", status_code=303)

@router.get("/map/{wid}/preview", response_class=HTMLResponse)
def wizard_preview(ctx: Ctx, request: Request, wid: str) -> Response:
    wiz = ctx.wiz_or_404(wid)
    if wiz.entity is None:
        return RedirectResponse(f"/map/{wid}/entity", status_code=303)
    rows = preview(wiz.sheet, wiz.mapping, limit=8)
    keys = [k for k in (f.key for f in FIELDS) if k in wiz.mapping.values()]
    return ctx.render(request, "wizard_preview.html.j2", wstep=4, wiz=wiz, rows=rows, keys=keys,
                  fields=FIELDS_BY_KEY)

@router.post("/map/{wid}/import")
def wizard_import(ctx: Ctx, request: Request, wid: str) -> Response:
    wiz = ctx.wiz_or_404(wid)
    if wiz.entity is None:
        return RedirectResponse(f"/map/{wid}/entity", status_code=303)
    raw, notes = build_raw(wiz.sheet, wiz.mapping, wiz.entity)
    ws = Workspace(wiz.sheet.source or "inventory", raw, kind="inventory")
    ws.import_notes = notes.summary()
    return ctx.add_workspace(ws, request)
