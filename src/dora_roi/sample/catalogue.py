"""Static catalogue of the fictional *Alpenrand* banking group used by the sample generator.

All organisations below are **fictional**. Names were chosen not to match real companies;
LEIs are generated with valid check digits from a hash of the name and do not correspond
to registered entities. Hyperscalers are represented by fictional groups (Nimbus, Stratus,
Cirrus) with a US parent and EU operating subsidiaries, to reproduce the typical pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dora_roi.model import EntityType, IctServiceType, Substitutability

S = IctServiceType


@dataclass(frozen=True)
class EntitySpec:
    key: str
    name: str
    country: str
    entity_type: EntityType
    authority: str
    total_assets: int
    parent: str | None  # key of parent (None = outside scope / holding)
    branches: tuple[tuple[str, str, str], ...] = ()  # (code, name, country)


@dataclass(frozen=True)
class FunctionSpec:
    capability: str
    name: str
    activity: str
    critical: bool
    rto: int
    rpo: int


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    country: str
    parent: str | None = None  # key of ultimate parent provider
    code_type: str = "LEI"
    euid: str | None = None
    additional: tuple[str, str] | None = None  # (code, type)
    latin_name: str | None = None


@dataclass(frozen=True)
class OfferingSpec:
    """An ICT service a provider sells to the group."""

    provider: str
    service: IctServiceType
    capabilities: tuple[str, ...]
    cost: tuple[int, int]  # annual cost range in EUR (per entity)
    substitutability: Substitutability = Substitutability.MEDIUM
    data: bool = True
    hosted_on: str | None = None  # rank-2 subcontractor
    rank3: str | None = None  # rank-3 subcontractor
    entities: tuple[str, ...] | None = None  # restrict to these entities
    group_master: bool = False  # overarching agreement signed by DE + call-offs
    reliance: str = "MATERIAL"


HOLDING_NAME = "Alpenrand Holding AG"

ENTITIES: tuple[EntitySpec, ...] = (
    EntitySpec("DE", "Alpenrand Bank (Europe) AG", "DE", EntityType.CREDIT_INSTITUTION, "BaFin",
               18_400_000_000, None,
               branches=(("ABE-IT-MIL", "Alpenrand Bank (Europe) AG – Succursale di Milano",
                          "IT"),)),
    EntitySpec("LU", "Alpenrand Banque Privée S.A.", "LU", EntityType.CREDIT_INSTITUTION, "CSSF",
               6_150_000_000, "DE",
               branches=(("ABP-FR-PAR", "Alpenrand Banque Privée – Succursale de Paris", "FR"),)),
    EntitySpec("AT", "Alpenrand Asset Management GmbH", "AT", EntityType.UCITS_MANCO, "FMA",
               410_000_000, "DE"),
)

FUNCTIONS: dict[str, tuple[FunctionSpec, ...]] = {
    "DE": (
        FunctionSpec("payments", "Payment processing (SEPA, instant, cross-border)",
                     "Payment services", True, 4, 0),
        FunctionSpec("core", "Core banking and account management", "Deposit taking", True, 4, 1),
        FunctionSpec("lending", "Lending and credit decisioning", "Lending", True, 24, 4),
        FunctionSpec("treasury", "Treasury and liquidity management", "Own-account dealing",
                     True, 8, 1),
        FunctionSpec("aml", "AML/KYC and sanctions screening", "Deposit taking", True, 8, 2),
        FunctionSpec("regrep", "Regulatory and statutory reporting", "Deposit taking", True,
                     72, 24),
        FunctionSpec("digital", "Digital and mobile banking channels", "Payment services", True,
                     4, 1),
        FunctionSpec("cards", "Card issuing and processing", "Payment services", True, 4, 0),
        FunctionSpec("secops", "IT security operations and identity management",
                     "Deposit taking", True, 4, 1),
        FunctionSpec("crm", "Customer relationship management", "Deposit taking", False, 48, 24),
        FunctionSpec("hr", "Human resources and payroll", "Deposit taking", False, 120, 24),
        FunctionSpec("marketdata", "Market data and pricing", "Own-account dealing", False, 24, 8),
        FunctionSpec("archive", "Document management and archiving", "Deposit taking", False,
                     120, 24),
        FunctionSpec("workplace", "Workplace collaboration and e-mail", "Deposit taking", False,
                     24, 4),
    ),
    "LU": (
        FunctionSpec("core", "Core banking and custody accounts", "Deposit taking", True, 4, 1),
        FunctionSpec("pms", "Portfolio management and investment advice",
                     "Portfolio management", True, 8, 4),
        FunctionSpec("payments", "Payment processing", "Payment services", True, 4, 0),
        FunctionSpec("aml", "Client onboarding, KYC and AML", "Deposit taking", True, 8, 2),
        FunctionSpec("custody", "Custody and securities settlement", "Safekeeping", True, 8, 1),
        FunctionSpec("regrep", "Regulatory reporting", "Deposit taking", True, 72, 24),
        FunctionSpec("clientrep", "Client reporting", "Portfolio management", False, 72, 24),
        FunctionSpec("crm", "Client relationship management", "Deposit taking", False, 48, 24),
        FunctionSpec("workplace", "Workplace collaboration and e-mail", "Deposit taking", False,
                     24, 4),
        FunctionSpec("secops", "IT security operations", "Deposit taking", True, 4, 1),
    ),
    "AT": (
        FunctionSpec("pms", "Portfolio management of UCITS funds", "Collective portfolio "
                     "management", True, 8, 4),
        FunctionSpec("fundacct", "Fund accounting and NAV calculation", "Collective portfolio "
                     "management", True, 24, 4),
        FunctionSpec("trading", "Order management and trade execution", "Collective portfolio "
                     "management", True, 4, 1),
        FunctionSpec("risk", "Investment risk management", "Collective portfolio management",
                     True, 24, 8),
        FunctionSpec("regrep", "Regulatory reporting", "Collective portfolio management", False,
                     72, 24),
        FunctionSpec("crm", "Distribution and client management", "Collective portfolio "
                     "management", False, 72, 24),
        FunctionSpec("workplace", "Workplace collaboration and e-mail", "Collective portfolio "
                     "management", False, 24, 4),
    ),
}

PROVIDERS: tuple[ProviderSpec, ...] = (
    # --- hyperscaler groups (US parent + EU operating entity)
    ProviderSpec("nimbus_us", "Nimbus Cloud Inc.", "US"),
    ProviderSpec("nimbus_eu", "Nimbus Cloud Services EMEA Ltd", "IE", parent="nimbus_us"),
    ProviderSpec("stratus_us", "Stratus Compute Corp.", "US"),
    ProviderSpec("stratus_eu", "Stratus Compute Europe S.à r.l.", "LU", parent="stratus_us"),
    ProviderSpec("cirrus_us", "Cirrus Platforms LLC", "US"),
    ProviderSpec("cirrus_eu", "Cirrus Platforms Ireland Ltd", "IE", parent="cirrus_us"),
    # --- intra-group shared service centre (outside the DORA scope of the register)
    ProviderSpec("services", "Alpenrand Services AG", "CH",
                 additional=("CHE-123.456.789", "VAT")),
    # --- banking applications
    ProviderSpec("helix", "Helix Core Banking AG", "CH", additional=("CHE-421.337.090", "VAT")),
    ProviderSpec("ledgerline", "Ledgerline Systems GmbH", "DE", code_type="EUID",
                 euid="DEK1101R.HRB206613"),
    ProviderSpec("kronos", "Kronos Payments B.V.", "NL"),
    ProviderSpec("cardstream", "CardStream Processing S.A.", "BE"),
    ProviderSpec("veritas", "Veritas KYC Solutions Ltd", "GB"),
    ProviderSpec("sentinel", "Sentinel Screening GmbH", "AT"),
    ProviderSpec("aurum", "Aurum Market Data S.A.", "FR"),
    ProviderSpec("quantra", "Quantra Analytics AG", "CH"),
    ProviderSpec("wealthbridge", "Wealthbridge Software Ltd", "GB"),
    ProviderSpec("treasuryone", "TreasuryOne SaaS GmbH", "DE"),
    ProviderSpec("regflow", "RegFlow Reporting S.A.", "LU"),
    ProviderSpec("customersphere", "CustomerSphere Inc.", "US"),
    ProviderSpec("peopleledger", "PeopleLedger SE", "DE"),
    ProviderSpec("mobilio", "Mobilio Digital Banking GmbH", "AT"),
    ProviderSpec("tradeport", "Tradeport Systems Ltd", "GB"),
    ProviderSpec("fundcalc", "Fundcalc Administration Services S.A.", "LU"),
    ProviderSpec("custodia", "Custodia Securities Platform S.p.A.", "IT"),
    ProviderSpec("creditum", "Creditum Data GmbH", "DE"),
    ProviderSpec("logscope", "Logscope Inc.", "US"),
    ProviderSpec("archiva", "Archiva Records AG", "CH"),
    ProviderSpec("vaultline", "Vaultline Backup Services Ltd", "IE"),
    ProviderSpec("clientview", "ClientView Reporting GmbH", "DE"),
    # --- infrastructure, network, telecom
    ProviderSpec("alpinetel", "Alpine Telecom AG", "CH"),
    ProviderSpec("eurolink", "EuroLink Carrier S.p.A.", "IT"),
    ProviderSpec("netwave", "Netwave Infrastructure GmbH", "DE"),
    ProviderSpec("rheinpark", "Rheinpark Datacenter GmbH", "DE"),
    ProviderSpec("luxhost", "Luxhost Data Centres S.A.", "LU"),
    ProviderSpec("nordicfibre", "Nordic Fibre AB", "SE"),
    ProviderSpec("finconnect", "FinConnect Service Bureau S.A.", "BE"),
    # --- security, services, development
    ProviderSpec("bastion", "Bastion Cyber Defence B.V.", "NL"),
    ProviderSpec("cipherwall", "Cipherwall Identity Ltd", "IE"),
    ProviderSpec("danubia", "Danubia IT Services Kft.", "HU", code_type="EUID",
                 euid="HUOCCSZ.01-09-562739"),
    ProviderSpec("codeforge", "Codeforge Solutions Sp. z o.o.", "PL"),
    ProviderSpec("nearshore", "Nearshore Dev Labs SRL", "RO"),
    ProviderSpec("meridian", "Meridian Technology Consulting GmbH", "DE"),
    ProviderSpec("vertex", "Vertex Hardware Distribution AG", "CH"),
    ProviderSpec("printlogic", "PrintLogic Output Services GmbH", "DE"),
    ProviderSpec("athena", "Athena Kyber Systems Μονοπρόσωπη Α.Ε.", "GR",
                 latin_name="Athena Kyber Systems Single Member S.A."),
)

ALL = ("DE", "LU", "AT")
NS, HC, MC, EZ = (Substitutability.NOT_SUBSTITUTABLE, Substitutability.HIGHLY_COMPLEX,
                  Substitutability.MEDIUM, Substitutability.EASY)

OFFERINGS: tuple[OfferingSpec, ...] = (
    # hyperscalers: group master agreements with call-offs
    OfferingSpec("nimbus_eu", S.S17, ("core", "payments", "digital", "pms", "fundacct", "risk"),
                 (900_000, 2_400_000), HC, hosted_on="nimbus_us", rank3="rheinpark",
                 group_master=True, reliance="FULL"),
    OfferingSpec("nimbus_eu", S.S18, ("lending", "aml", "treasury", "trading"),
                 (300_000, 900_000), HC, hosted_on="nimbus_us", group_master=True),
    OfferingSpec("stratus_eu", S.S17, ("regrep", "archive", "clientrep"), (250_000, 700_000),
                 MC, hosted_on="stratus_us", group_master=True),
    OfferingSpec("cirrus_eu", S.S19, ("workplace", "crm", "secops"), (400_000, 1_100_000), HC,
                 hosted_on="cirrus_us", group_master=True, reliance="FULL"),
    OfferingSpec("nimbus_us", S.S13, ("secops",), (60_000, 120_000), MC, data=False,
                 entities=("DE",)),
    # intra-group shared services
    OfferingSpec("services", S.S14, ("core", "payments", "custody", "fundacct"),
                 (1_200_000, 3_000_000), HC, hosted_on="luxhost", reliance="FULL"),
    OfferingSpec("services", S.S03, ("workplace",), (200_000, 450_000), EZ, data=False),
    # core banking
    OfferingSpec("helix", S.S13, ("core",), (1_500_000, 3_200_000), NS, data=False,
                 entities=("DE", "LU"), reliance="FULL"),
    OfferingSpec("helix", S.S14, ("core",), (600_000, 1_100_000), NS, hosted_on="stratus_eu",
                 entities=("DE", "LU"), reliance="FULL"),
    # payments & cards
    OfferingSpec("ledgerline", S.S19, ("payments",), (700_000, 1_400_000), HC,
                 hosted_on="nimbus_eu", rank3="nimbus_us", entities=("DE", "LU"),
                 reliance="FULL"),
    OfferingSpec("kronos", S.S08, ("payments",), (350_000, 800_000), MC, entities=("DE", "LU")),
    OfferingSpec("cardstream", S.S08, ("cards",), (900_000, 1_600_000), HC, hosted_on="luxhost",
                 entities=("DE",), reliance="FULL"),
    OfferingSpec("finconnect", S.S11, ("payments", "custody", "treasury"), (180_000, 350_000),
                 MC, entities=("DE", "LU")),
    # KYC / AML
    OfferingSpec("veritas", S.S19, ("aml",), (250_000, 600_000), MC, hosted_on="cirrus_eu",
                 entities=("DE", "LU")),
    OfferingSpec("sentinel", S.S19, ("aml",), (120_000, 300_000), EZ, hosted_on="nimbus_eu",
                 entities=("DE", "LU")),
    OfferingSpec("creditum", S.S05, ("lending",), (90_000, 200_000), MC, entities=("DE",)),
    # treasury, markets, risk
    OfferingSpec("treasuryone", S.S19, ("treasury",), (300_000, 650_000), MC,
                 hosted_on="stratus_eu", entities=("DE",)),
    OfferingSpec("aurum", S.S05, ("marketdata", "pms", "trading", "risk"), (150_000, 420_000),
                 MC, data=False),
    OfferingSpec("quantra", S.S06, ("risk", "treasury", "lending"), (180_000, 380_000), MC,
                 hosted_on="nimbus_eu"),
    OfferingSpec("tradeport", S.S13, ("trading",), (300_000, 520_000), HC, entities=("AT",)),
    OfferingSpec("fundcalc", S.S19, ("fundacct",), (450_000, 800_000), HC,
                 hosted_on="stratus_eu", rank3="stratus_us", entities=("AT",), reliance="FULL"),
    # wealth & custody
    OfferingSpec("wealthbridge", S.S19, ("pms", "clientrep"), (500_000, 1_000_000), HC,
                 hosted_on="nimbus_eu", rank3="rheinpark", entities=("LU", "AT"),
                 reliance="FULL"),
    OfferingSpec("custodia", S.S19, ("custody",), (400_000, 750_000), HC, hosted_on="luxhost",
                 entities=("LU",)),
    OfferingSpec("clientview", S.S19, ("clientrep",), (80_000, 160_000), EZ,
                 hosted_on="cirrus_eu", entities=("LU",)),
    # regulatory reporting
    OfferingSpec("regflow", S.S19, ("regrep",), (220_000, 480_000), MC, hosted_on="stratus_eu"),
    # digital channels
    OfferingSpec("mobilio", S.S19, ("digital",), (600_000, 1_200_000), HC,
                 hosted_on="cirrus_eu", entities=("DE",), reliance="FULL"),
    OfferingSpec("codeforge", S.S02, ("digital", "lending"), (300_000, 700_000), EZ, data=False,
                 entities=("DE",)),
    OfferingSpec("nearshore", S.S02, ("pms", "core"), (150_000, 350_000), EZ, data=False,
                 entities=("LU",)),
    # CRM, HR, archive, observability, backup
    OfferingSpec("customersphere", S.S19, ("crm",), (200_000, 450_000), MC,
                 hosted_on="stratus_us"),
    OfferingSpec("peopleledger", S.S19, ("hr",), (150_000, 260_000), EZ, hosted_on="nimbus_eu",
                 entities=("DE",)),
    OfferingSpec("archiva", S.S09, ("archive",), (90_000, 180_000), EZ, entities=("DE",)),
    OfferingSpec("logscope", S.S19, ("secops",), (120_000, 260_000), MC, hosted_on="nimbus_us",
                 entities=("DE", "LU")),
    OfferingSpec("vaultline", S.S09, ("core", "custody"), (140_000, 300_000), MC,
                 hosted_on="stratus_eu", entities=("DE", "LU")),
    # security
    OfferingSpec("bastion", S.S04, ("secops",), (350_000, 700_000), MC, entities=("DE", "LU")),
    OfferingSpec("cipherwall", S.S19, ("secops", "digital"), (160_000, 340_000), HC,
                 hosted_on="cirrus_eu", entities=("DE", "LU")),
    OfferingSpec("athena", S.S16, ("secops",), (40_000, 90_000), EZ, data=False,
                 entities=("DE",)),
    # infrastructure & telecom
    OfferingSpec("rheinpark", S.S07, ("core", "payments", "cards", "treasury"),
                 (400_000, 900_000), MC, entities=("DE",)),
    OfferingSpec("luxhost", S.S07, ("core", "custody", "payments"), (300_000, 600_000), MC,
                 entities=("LU",)),
    OfferingSpec("alpinetel", S.S10, ("payments", "core", "workplace"), (120_000, 280_000), EZ,
                 data=False),
    OfferingSpec("eurolink", S.S10, ("payments", "trading", "workplace"), (90_000, 200_000), EZ,
                 data=False, hosted_on="nordicfibre"),
    OfferingSpec("netwave", S.S11, ("core", "payments", "digital"), (200_000, 450_000), MC,
                 data=False, entities=("DE",)),
    OfferingSpec("danubia", S.S03, ("workplace", "crm"), (150_000, 320_000), EZ),
    OfferingSpec("danubia", S.S14, ("core", "lending"), (250_000, 500_000), MC,
                 entities=("DE",)),
    OfferingSpec("vertex", S.S12, ("workplace", "trading"), (80_000, 200_000), EZ, data=False),
    OfferingSpec("printlogic", S.S14, ("clientrep", "archive"), (60_000, 140_000), EZ,
                 entities=("DE", "LU")),
    OfferingSpec("meridian", S.S15, ("regrep", "lending", "treasury"), (120_000, 300_000), EZ,
                 data=False, entities=("DE",)),
    OfferingSpec("meridian", S.S01, ("digital", "core"), (180_000, 360_000), EZ, data=False,
                 entities=("DE",)),
    # maintenance / support contracts alongside the main application contracts
    OfferingSpec("ledgerline", S.S14, ("payments",), (150_000, 300_000), HC, data=False,
                 entities=("DE", "LU")),
    OfferingSpec("wealthbridge", S.S14, ("pms",), (120_000, 260_000), HC, data=False,
                 entities=("LU", "AT")),
    OfferingSpec("cardstream", S.S03, ("cards",), (80_000, 160_000), EZ, data=False,
                 entities=("DE",)),
    OfferingSpec("alpinetel", S.S11, ("digital", "crm", "pms"), (60_000, 140_000), EZ,
                 data=False),
    OfferingSpec("codeforge", S.S02, ("trading", "pms"), (90_000, 200_000), EZ, data=False,
                 entities=("AT",)),
)


@dataclass
class Catalogue:
    entities: tuple[EntitySpec, ...] = ENTITIES
    functions: dict[str, tuple[FunctionSpec, ...]] = field(default_factory=lambda: FUNCTIONS)
    providers: tuple[ProviderSpec, ...] = PROVIDERS
    offerings: tuple[OfferingSpec, ...] = OFFERINGS
