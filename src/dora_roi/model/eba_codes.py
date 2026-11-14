"""Official EBA taxonomy members for the DORA register of information (reporting framework 4.0).

The tables were taken from the EBA files in ``reference/eba/`` (see its README for provenance
and checksums); the long lists at the end were generated from them. Refresh this module when
the EBA publishes a new reporting framework version.

* ``CODE_MAP`` - toolkit code list -> internal code -> taxonomy member, from the *List of
  possible values for all data fields with drop downs* (3 March 2025) and the *Annotated Table
  Layout DORA 4.0*. It is the default code map of the xBRL-CSV exporter.
* ``BOOLEAN_MEMBERS`` - columns the toolkit models as booleans but the DPM reports as an
  enumeration (e.g. ``eba_BT:x28`` = yes).
* ``LICENSED_ACTIVITIES`` - B_06.01 c0020 members and labels (DPM hierarchy TA5).
* ``EBA_COUNTRIES`` / ``EBA_CURRENCIES`` - members of the DPM country and currency hierarchies.
"""

from __future__ import annotations

from functools import cache

#: Framework the tables were taken from.
FRAMEWORK = "EBA reporting framework 4.0 (DPM 4.0, taxonomy package 4.0 errata 5)"

#: ``eba_GA`` member for "Not applicable" in country key fields (FAQ Q59, Q61, Q63).
COUNTRY_NOT_APPLICABLE = "qx2007"
#: Value typed into key / foreign-key text fields that have no value (FAQ Q26, Q64, Q124).
TEXT_NOT_APPLICABLE = "Not Applicable"


@cache
def _licensed_maps() -> tuple[dict[str, str], dict[str, str]]:
    by_label = {label.casefold(): code for code, label in LICENSED_ACTIVITIES}
    label_by_code: dict[str, str] = {}
    for code, label in LICENSED_ACTIVITIES:
        label_by_code.setdefault(code, label)
    return by_label, label_by_code


def licensed_activity_code(value: str) -> str | None:
    """EBA member (``eba_TA:x…``) for a B_06.01 c0020 value given as member, code or label."""
    by_label, label_by_code = _licensed_maps()
    text = value.strip()
    if text.startswith("eba_TA:") and text in label_by_code:
        return text
    if f"eba_TA:{text}" in label_by_code:
        return f"eba_TA:{text}"
    return by_label.get(text.casefold())


def licensed_activity_label(code: str) -> str:
    """First EBA label of a licensed-activity member (the member itself if unknown)."""
    return _licensed_maps()[1].get(code, code)

CODE_MAP: dict[str, dict[str, str]] = {
    # B_01.01 / B_01.02 c0040 - hierarchies CT6 (financial entities) and CT61 (+ non-financial)
    "EntityType": {
        "CREDIT_INSTITUTION": "eba_CT:x12",
        "PAYMENT_INSTITUTION": "eba_CT:x300",
        "ACCOUNT_INFORMATION_SP": "eba_CT:x301",
        "E_MONEY_INSTITUTION": "eba_CT:x302",
        "INVESTMENT_FIRM": "eba_CT:x599",
        "CASP": "eba_CT:x303",
        "ART_ISSUER": "eba_CT:x310",
        "CSD": "eba_CT:x304",
        "CCP": "eba_CT:x643",
        "TRADING_VENUE": "eba_CT:x305",
        "TRADE_REPOSITORY": "eba_CT:x306",
        "AIFM": "eba_CT:x307",
        "UCITS_MANCO": "eba_CT:x639",
        "DRSP": "eba_CT:x308",
        "INSURANCE_UNDERTAKING": "eba_CT:x309",
        "INSURANCE_INTERMEDIARY": "eba_CT:x320",
        "IORP": "eba_CT:x311",
        "CRA": "eba_CT:x312",
        "BENCHMARK_ADMINISTRATOR": "eba_CT:x313",
        "CROWDFUNDING_SP": "eba_CT:x314",
        "SECURITISATION_REPOSITORY": "eba_CT:x315",
        "OTHER_FINANCIAL": "eba_CT:x316",
        "NON_FINANCIAL_ICT_INTRAGROUP": "eba_CT:x317",
        "OTHER": "eba_CT:x318",
    },
    # B_01.02 c0050 - RP8
    "HierarchyInGroup": {
        "ULTIMATE_PARENT": "eba_RP:x53",
        "PARENT": "eba_RP:x551",
        "SUBSIDIARY": "eba_RP:x56",
        "NOT_IN_GROUP": "eba_RP:x21",
        "OUTSOURCING": "eba_RP:x210",
    },
    # B_02.01 c0020 - CO1
    "ContractType": {
        "STANDALONE": "eba_CO:x1",
        "OVERARCHING": "eba_CO:x2",
        "SUBSEQUENT": "eba_CO:x3",
    },
    # every "type of code" column - qCO:new_CO2
    "ProviderCodeType": {
        "LEI": "eba_qCO:qx2000",
        "NIN": "eba_qCO:qx2001",
        "EUID": "eba_qCO:qx2002",
        "CRN": "eba_qCO:qx2003",
        "VAT": "eba_qCO:qx2004",
        "PNR": "eba_qCO:qx2005",
    },
    "AdditionalCodeType": {
        "LEI": "eba_qCO:qx2000",
        "NIN": "eba_qCO:qx2001",
        "EUID": "eba_qCO:qx2002",
        "CRN": "eba_qCO:qx2003",
        "VAT": "eba_qCO:qx2004",
        "PNR": "eba_qCO:qx2005",
    },
    # B_05.01 c0070 - CT7
    "PersonType": {
        "LEGAL": "eba_CT:x212",
        "NATURAL": "eba_CT:x213",
    },
    # B_02.02 c0060, B_05.02 c0020, B_07.01 c0040 - TA4
    "IctServiceType": {f"S{i:02d}": f"eba_TA:S{i:02d}" for i in range(1, 20)},
    # B_02.02 c0090 - CO2
    "TerminationReason": {
        "EXPIRED": "eba_CO:x4",
        "BREACH_OF_LAW": "eba_CO:x5",
        "PERFORMANCE": "eba_CO:x6",
        "DATA_SECURITY": "eba_CO:x7",
        "AUTHORITY_REQUEST": "eba_CO:x8",
        "OTHER": "eba_CO:x9",
    },
    # B_02.02 c0170 - ZZ92
    "DataSensitivity": {
        "LOW": "eba_ZZ:x791",
        "MEDIUM": "eba_ZZ:x792",
        "HIGH": "eba_ZZ:x793",
    },
    # B_02.02 c0180 - ZZ91
    "RelianceLevel": {
        "NOT_SIGNIFICANT": "eba_ZZ:x794",
        "LOW": "eba_ZZ:x795",
        "MATERIAL": "eba_ZZ:x796",
        "FULL": "eba_ZZ:x797",
    },
    # B_06.01 c0050 - BT14
    "Criticality": {
        "CRITICAL": "eba_BT:x28",
        "NOT_CRITICAL": "eba_BT:x29",
        "NOT_ASSESSED": "eba_BT:x21",
    },
    # B_06.01 c0100 (ZZ114) and B_07.01 c0100 (ZZ113)
    "Impact": {
        "LOW": "eba_ZZ:x791",
        "MEDIUM": "eba_ZZ:x792",
        "HIGH": "eba_ZZ:x793",
        "NOT_ASSESSED": "eba_ZZ:x799",
    },
    # B_07.01 c0050 - ZZ110
    "Substitutability": {
        "NOT_SUBSTITUTABLE": "eba_ZZ:x959",
        "HIGHLY_COMPLEX": "eba_ZZ:x960",
        "MEDIUM": "eba_ZZ:x961",
        "EASY": "eba_ZZ:x962",
    },
    # B_07.01 c0060 - ZZ111
    "NonSubstitutabilityReason": {
        "NO_ALTERNATIVES": "eba_ZZ:x963",
        "MIGRATION": "eba_ZZ:x964",
        "BOTH": "eba_ZZ:x965",
        "NOT_APPLICABLE": "eba_ZZ:x0",
    },
    # B_07.01 c0090 - ZZ112
    "Reintegration": {
        "EASY": "eba_ZZ:x798",
        "DIFFICULT": "eba_ZZ:x966",
        "HIGHLY_COMPLEX": "eba_ZZ:x967",
    },
    # B_07.01 c0110 - BT13
    "AlternativesIdentified": {
        "YES": "eba_BT:x28",
        "NO": "eba_BT:x29",
        "NOT_ASSESSED": "eba_BT:x21",
    },
}

#: ``{(template, column): (member for true, member for false)}``. The other boolean columns
#: are the technical "Link" columns, reported as ``true`` (DPM ``trueItemType``).
BOOLEAN_MEMBERS: dict[tuple[str, str], tuple[str, str]] = {
    ("B_02.02", "c0140"): ("eba_BT:x28", "eba_BT:x29"),  # storage of data - BT4
    ("B_04.01", "c0030"): ("eba_ZZ:x838", "eba_ZZ:x839"),  # branch / not a branch - ZZ93
    ("B_07.01", "c0080"): ("eba_BT:x28", "eba_BT:x29"),  # existence of an exit plan - BT4
}


# ---- GENERATED by scripts/gen_eba_codes.py from reference/eba - do not edit below ----

#: B_06.01 c0020 - ``(member, label)``; a member may appear with several label variants.
LICENSED_ACTIVITIES: tuple[tuple[str, str], ...] = (
    ('eba_TA:x28', 'Payment services'),
    ('eba_TA:x104', 'Foreign exchange services'),
    ('eba_TA:x133', 'Reception and transmission of orders in relation to one or more financial instruments'),
    ('eba_TA:x133', 'reception and transmission of orders in relation to financial instruments'),
    ('eba_TA:x134', 'Execution of orders on behalf of clients'),
    ('eba_TA:x136', 'Portfolio management'),
    ('eba_TA:x137', 'Investment advice'),
    ('eba_TA:x137', 'investment advice'),
    ('eba_TA:x138', 'Underwriting of financial instruments and/or placing of financial instruments on a firm commitment basis'),
    ('eba_TA:x139', 'Placing of financial instruments without a firm commitment basis'),
    ('eba_TA:x140', 'Operation of an MTF'),
    ('eba_TA:x141', 'Operation of an OTF'),
    ('eba_TA:x143', 'Granting credits or loans to an investor'),
    ('eba_TA:x144', 'Advice to undertakings'),
    ('eba_TA:x146', 'Investment research and financial analysis'),
    ('eba_TA:x147', 'Services related to underwriting'),
    ('eba_TA:x162', 'Taking deposits and other repayable funds'),
    ('eba_TA:x163', 'Lending activities'),
    ('eba_TA:x164', 'Financial leasing'),
    ('eba_TA:x165', 'Issuing and administering other means of payment'),
    ('eba_TA:x166', 'Guarantees and commitments'),
    ('eba_TA:x167', 'Guarantees and commitments related to securities lending and borrowing, within the meaning of point 6 of Annex I to Directive 2013/36/EU'),
    ('eba_TA:x168', 'Trading for own account or for account of customers'),
    ('eba_TA:x169', 'Participation in securities issues and the provision of services relating to such issues'),
    ('eba_TA:x170', 'Advisory services'),
    ('eba_TA:x171', 'Money broking'),
    ('eba_TA:x172', 'Portfolio management and advice'),
    ('eba_TA:x173', 'Dealing on own account'),
    ('eba_TA:x174', 'Safekeeping and administration of securities'),
    ('eba_TA:x175', 'Safekeeping and administration of financial instruments for the account of clients'),
    ('eba_TA:x176', 'safe-keeping and administration in relation to shares or units of collective investment undertakings'),
    ('eba_TA:x177', 'non-core services (safekeeping and administration in relation to units of collective investment undertakings)'),
    ('eba_TA:x178', 'Safe custody services'),
    ('eba_TA:x179', 'Credit reference services'),
    ('eba_TA:x180', 'Issuing electronic money'),
    ('eba_TA:x181', 'reception and transmission of orders for crypto-assets on behalf of clients'),
    ('eba_TA:x182', 'Portfolio management on crypto-assets'),
    ('eba_TA:x183', 'management of portfolios of investments (AIFMD)'),
    ('eba_TA:x184', 'management of portfolios of investments (UCITSD)'),
    ('eba_TA:x185', 'Non-Life Insurance: Classes 1 and 2: ‘Accident and Health Insurance’'),
    ('eba_TA:x186', 'Non-Life Insurance: Classes 1 (fourth indent), 3, 7 and 10: ‘Motor Insurance’'),
    ('eba_TA:x187', 'Non-Life Insurance: Classes 1 (fourth indent), 4, 6, 7 and 12: ‘Marine and Transport Insurance’'),
    ('eba_TA:x188', 'Non-Life Insurance: Classes 1 (fourth indent), 5, 7 and 11: ‘Aviation Insurance’'),
    ('eba_TA:x189', 'Non-Life Insurance: Classes 8 and 9: ‘Insurance against Fire and other Damage to Property’'),
    ('eba_TA:x190', 'Non-Life Insurance: Classes 10, 11, 12 and 13: ‘Liability Insurance’'),
    ('eba_TA:x191', 'Non-Life Insurance: Classes 14 and 15: ‘Credit and Suretyship Insurance’'),
    ('eba_TA:x192', 'Non-Life Insurance: All classes, at the choice of the Member States, which shall notify the other Member States and the Commission of their choice'),
    ('eba_TA:x193', 'Life Insurance: The life insurance referred to in points (a)(i), (ii) and (iii) of Article 2(3) excluding those referred to in II and III'),
    ('eba_TA:x194', 'Life Insurance: Marriage assurance, birth assurance'),
    ('eba_TA:x195', 'Life Insurance: The insurance referred to in points (a)(i) and (ii) of Article 2(3), which are linked to investment funds'),
    ('eba_TA:x196', 'Life Insurance: Permanent health insurance, referred to in point (a)(iv) of Article 2(3)'),
    ('eba_TA:x197', 'Life Insurance: Tontines, referred to in point (b)(i) of Article 2(3)'),
    ('eba_TA:x198', 'Life Insurance: Capital redemption operations, referred to in point (b)(ii) of Article 2(3)'),
    ('eba_TA:x199', 'Life Insurance: Management of group pension funds, referred to in point (b)(iii) and (iv) of Article 2(3)'),
    ('eba_TA:x200', 'Life Insurance: The operations referred to in point (b)(v) of Article 2(3)'),
    ('eba_TA:x201', 'Life Insurance: The operations referred to in Article 2(3)(c)'),
    ('eba_TA:x202', 'insurance distribution'),
    ('eba_TA:x203', 'reinsurance distribution'),
    ('eba_TA:x204', 'Investment services related to the underlying of the derivatives'),
    ('eba_TA:x205', 'Retirement-benefit related operations and activities arising therefrom'),
    ('eba_TA:x206', 'issuance of credit ratings'),
    ('eba_TA:x207', 'administering the arrangements for determining a benchmark'),
    ('eba_TA:x208', 'collecting, analysing or processing input data for the purpose of determining a benchmark'),
    ('eba_TA:x209', 'determining a benchmark through the application of a formula or other method of calculation or by an assessment of input data provided for that purpose'),
    ('eba_TA:x210', 'publication of benchmark'),
    ('eba_TA:x211', 'Provision of crowdfunding services'),
    ('eba_TA:x212', 'ancillary non-securitisation services'),
    ('eba_TA:x213', 'ancillary securitisation services'),
    ('eba_TA:x214', 'collection and maintenance of the records of derivatives (non-SFTs)'),
    ('eba_TA:x215', 'collection and maintenance of the records of SFTs'),
    ('eba_TA:x216', 'collection and maintenance of the records of securitisations'),
    ('eba_TA:x217', 'activity as approved publication arrangement'),
    ('eba_TA:x218', 'activity as consolidated tape provider'),
    ('eba_TA:x219', 'activity as approved reporting mechanism'),
    ('eba_TA:x220', 'Services enabling cash to be placed on a payment account as well as all the operations required for operating a payment account'),
    ('eba_TA:x221', 'Services enabling cash withdrawals from a payment account as well as all the operations required for operating a payment account'),
    ('eba_TA:x222', 'Execution of payment transactions, including transfers of funds on a payment account with the user’s payment service provider or with another payment service provider'),
    ('eba_TA:x223', 'Execution of payment transactions where the funds are covered by a credit line for a payment service user'),
    ('eba_TA:x224', 'Issuing of payment instruments and/or acquiring of payment transactions'),
    ('eba_TA:x225', 'Money remittance'),
    ('eba_TA:x226', 'Payment initiation services'),
    ('eba_TA:x227', 'Account information services'),
    ('eba_TA:x228', 'providing custody and administration of crypto-assets on behalf of clients'),
    ('eba_TA:x229', 'operation of a trading platform for crypto-assets'),
    ('eba_TA:x230', 'Operation of a Regulated Market'),
    ('eba_TA:x231', 'exchange of crypto-assets for funds'),
    ('eba_TA:x232', 'exchange of crypto-assets for other crypto-assets'),
    ('eba_TA:x233', 'execution of orders for crypto-assets on behalf of clients'),
    ('eba_TA:x234', 'placing of crypto-assets'),
    ('eba_TA:x235', 'providing advice on crypto-assets'),
    ('eba_TA:x236', 'providing transfer services for crypto-assets on behalf of clients'),
    ('eba_TA:x237', 'issuance of asset-referenced tokens'),
    ('eba_TA:x238', 'Initial recording of securities in a book-entry system (‘notary service’)'),
    ('eba_TA:x239', 'Providing and maintaining securities accounts at the top tier level (‘central maintenance service’)'),
    ('eba_TA:x240', 'Operating a securities settlement system (‘settlement service’)'),
    ('eba_TA:x241', 'Organising a securities lending mechanism, as agent among participants of a securities settlement system'),
    ('eba_TA:x242', 'Providing collateral management services, as agent for participants in a securities settlement system'),
    ('eba_TA:x243', 'Providing general collateral management services as agent'),
    ('eba_TA:x244', 'Establishing CSD links, providing, maintaining or operating securities accounts in relation to the settlement service, collateral management, other ancillary services'),
    ('eba_TA:x245', 'Settlement matching, instruction routing, trade confirmation, trade verification'),
    ('eba_TA:x246', 'Services related to shareholders’ registers'),
    ('eba_TA:x247', 'Supporting the processing of corporate actions, including tax, general meetings and information services'),
    ('eba_TA:x248', 'New issue services, including allocation and management of ISIN codes and similar codes'),
    ('eba_TA:x249', 'Instruction routing and processing, fee collection and processing and related reporting'),
    ('eba_TA:x250', 'Providing regulatory reporting'),
    ('eba_TA:x251', 'Providing information, data and statistics to market/census bureaus or other governmental or inter-governmental entities'),
    ('eba_TA:x252', 'Providing IT services'),
    ('eba_TA:x253', 'Providing cash accounts to, and accepting deposits from, participants in a securities settlement system and holders of securities accounts, within the meaning of point 1 of Annex I to Directive 2013/36/EU'),
    ('eba_TA:x254', 'Providing cash credit for reimbursement no later than the following business day, cash lending to pre-finance corporate actions and lending securities to holders of securities accounts, within the meaning of point 2 of Annex I to Directive 2013/36/EU'),
    ('eba_TA:x255', 'Payment services involving processing of cash and foreign exchange transactions, within the meaning of point 4 of Annex I to Directive 2013/36/EU'),
    ('eba_TA:x256', 'Treasury activities involving foreign exchange and transferable securities related to managing participants’ long balances, within the meaning of points 7(b) and (e) of Annex I to Directive 2013/36/EU'),
    ('eba_TA:x257', 'Any other NCA-permitted non-banking-type ancillary services not specified in Annex of Regulation (EU) No 909/2014 (CSDR) - Section B'),
    ('eba_TA:x258', 'Any other NCA-permitted Banking-type ancillary services not specified in Annex of Regulation (EU) No 909/2014 (CSDR) - Section C'),
    ('eba_TA:x259', 'interposition between counterparties to contracts traded on one or more financial markets'),
    ('eba_TA:x260', 'risk management'),
    ('eba_TA:x261', 'legal and fund management accounting services'),
    ('eba_TA:x262', 'customer inquiries'),
    ('eba_TA:x263', 'valuation and pricing, including tax returns'),
    ('eba_TA:x263', 'valuation and pricing (including tax returns)'),
    ('eba_TA:x264', 'regulatory compliance monitoring'),
    ('eba_TA:x265', 'maintenance of unit-/shareholder register'),
    ('eba_TA:x266', 'unit/shares issues and redemptions'),
    ('eba_TA:x267', 'maintenance of unit-holder register'),
    ('eba_TA:x268', 'unit issues and redemptions'),
    ('eba_TA:x269', 'contract settlements, including certificate dispatch'),
    ('eba_TA:x269', 'contract settlements (including certificate dispatch)'),
    ('eba_TA:x270', 'distribution of income'),
    ('eba_TA:x271', 'record keeping'),
    ('eba_TA:x272', 'Marketing'),
    ('eba_TA:x273', 'Activities related to the assets of AIFs, namely services necessary to meet the fiduciary duties of the AIFM'),
    ('eba_TA:x274', 'Investment advice concerning one or more of the instruments listed in Annex I, Section C to Directive 2004/39/EC'),
    ('eba_TA:x275', 'Ancillary services'),
    ('eba_TA:x276', 'Supporting function'),
    ('eba_TA:qx277', 'Non-life reinsurance activities'),
    ('eba_TA:qx278', 'Life-reinsurance activities'),
)

#: Members of the DPM country hierarchy (``eba_GA:``) apart from ``x28`` and ``qx2007``.
EBA_COUNTRIES: frozenset[str] = frozenset("""
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
    BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR
    CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF
    PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI
    SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
    TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW
""".split())

#: Members of the DPM currency hierarchy ``CU3_4_WITHOUT_X0`` (``eba_CU:``).
EBA_CURRENCIES: frozenset[str] = frozenset("""
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV
    BRL BSD BTN BWP BYN BYR BZD CAD CDF CHE CHF CHW CLF CLP CNH CNY COP COU CRC CUC
    CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ
    GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW
    KRW KWD KYD KZT LAK LBP LKR LRD LSL LTL LVL LYD MAD MDL MGA MKD MMK MNT MOP MRO
    MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG
    QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLL SOS SRD SSP STD SVC SYP SZL
    THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYI UYU UZS VEF VND VUV WST XCD
    XPF YER ZAR ZMK ZMW ZWL
""".split())

#: Official checks of the EBA overview of 28 April 2025: ``{id: (family, table, status, summary)}``
#: with family ``technical``, ``dpm`` (DPM validation rule) or ``business`` (GLEIF/BRIS lookup).
OFFICIAL_CHECKS: dict[str, tuple[str, str, str, str]] = {
    '101': ('technical', '', 'active', 'Report filename extension must be zip'),
    '102': ('technical', '', 'active', 'SFTP report file size must not exceed 10GB'),
    '103': ('technical', '', 'active', 'ZIP consistency (checksum, unzips correctly).'),
    '104': ('technical', '', 'active', "Filename allowed characters: alphanumeric plus hyphens ('-'), underscores ('_') and dots ('.')"),
    '105': ('technical', '', 'active', 'Filename structure (ReportSubject_Country_FrameworkCodeModuleVersion_Module_ReferenceDate_CreationTimestamp)'),
    '106': ('technical', '', 'active', 'Filename module inconsistency with the report category (SUP, REM, RES,PAY,DORA,PILLAR3)'),
    '107': ('technical', '', 'active', 'For CA submitted reports, the submission path country must match the filename country code'),
    '109': ('technical', '', 'active', "Filename reference date is valid date with format 'yyyy-mm-dd'"),
    '110': ('technical', '', 'active', 'Each submitted report filename must be unique - duplicate filenames are not allowed'),
    '111': ('technical', '', 'active', 'Reference date in the filename cannot be in the future'),
    '115': ('technical', '', 'active', 'DORA submitted report files must be a zip containing plain-csv'),
    '306': ('technical', '', 'active', 'XBRL instance documents must use UTF-8 encoding.'),
    '701': ('technical', '', 'active', 'CSV zip file must contain reports/report.json, reports/FilingIndicators.csv and reports/parameters.csv files and must be non-empty'),
    '702': ('technical', '', 'active', 'Invalid declarations in FilingIndicators.csv - wrong number of columns reported'),
    '703': ('technical', '', 'active', 'Each template can be declared only once in FilingIndicators.csv'),
    '704': ('technical', '', 'active', 'Only boolean values (true, false, 1, 0) are allowed for any template code in FilingIndicators.csv'),
    '705': ('technical', '', 'active', 'Missing filing indicator value - the true/false value is missing - only template code is present'),
    '714': ('technical', '', 'active', "The 'entityID' parameter must exist and its value must match filename"),
    '720': ('technical', '', 'active', 'Valid table names must be used as .csv filenames'),
    '723': ('technical', '', 'active', 'The header row in parameters.csv must consist only of the values name and value, in the first and second columns, respectively.'),
    '724': ('technical', '', 'active', 'No data was integratable - integrated'),
    '801': ('technical', '', 'active', 'All the header column codes must be defined in the taxonomy json files (in DPM)'),
    '802': ('technical', '', 'active', 'No column can be reported twice'),
    '803': ('technical', '', 'active', 'For closed tables, all the row identifier must match those in the dpm'),
    '804': ('technical', '', 'active', 'For closed tables, No row identifier can be reported twice'),
    '805': ('technical', '', 'active', 'For open tables, the key columns values cannot be empty'),
    '807': ('technical', '', 'active', 'The reported data must follow the key-foreign key contraints defined in the DPM'),
    '808': ('technical', '', 'active', 'All filing indicators have to be sent as true - and the templates reported empty if no data is present'),
    '809': ('technical', '', 'active', 'CSV formatting problem detected'),
    '305': ('technical', '', 'active', 'Numeric fact must not be reported with a string value'),
    '320': ('technical', '', 'active', 'Reference date inside an instance as well as within filename must be valid (FR 2.13, FR 2.10)'),
    '330': ('technical', '', 'active', "Date type metric must be reported with format 'yyyy-mm-dd'"),
    '331': ('technical', '', 'active', 'Integer type metric must be reported with an integer'),
    '332': ('technical', '', 'active', 'Boolean type metric must be reported with a boolean value (true/false/1/0)'),
    '333': ('technical', '', 'active', 'trueItemType must be reported with true value'),
    '503': ('technical', '', 'active', 'Extensible main property and explicit key dimension must only be reported with one of the restricted value of a hierarchy'),
    '505': ('technical', '', 'active', 'Each report must contain a report.json and this one must point to entrypoint json file for the module'),
    '510': ('technical', '', 'active', 'The values of filing indicators MUST only be those given by the label resources with the role http://www.eurofiling.info/xbrl/role/filing-indicator-code (the values are also present in TemplateCode field of Template table in DPM) (FR 1.6.3)'),
    '512': ('technical', '', 'active', 'The module referenced by the instance document must not refer to a taxonomy having FromDate = ToDate'),
    '514': ('technical', '', 'active', "Reporting subject must include entity type with '.' qualifier if the reference date is on or after 2022-12-31, and the module code does not contain CON or IND"),
    '806': ('technical', '', 'active', 'For open tables, you cannot have multiple rows with identical key values'),
    'e23674_e': ('dpm', 'B_05.01', 'active', 'B_05.01 c0020, c0050, c0060, c0070, c0080, c0110 must be reported'),
    'e23675_e': ('dpm', 'B_01.03', 'active', 'B_01.03 c* must be reported'),
    'e23676_e': ('dpm', 'B_01.02', 'active', 'B_01.02 c0020-0090 must be reported'),
    'e23677_e': ('dpm', 'B_01.01', 'active', 'B_01.01 c* must be reported'),
    'e23680_e': ('dpm', 'B_02.02', 'active', 'B_02.02 c0040-0080 must be reported'),
    'e23681_e': ('dpm', 'B_07.01', 'inactive', 'B_07.01 c0050, c0070, c0080, c0090, c0100, c0110 must be reported'),
    'e23682_e': ('dpm', 'B_06.01', 'active', 'B_06.01 c0020, c0030, c0050, c0070, c0080, c0090, c0100 must be reported'),
    'e23683_e': ('dpm', 'B_04.01', 'active', 'B_04.01 c0030 must be reported'),
    'e23792_e': ('dpm', 'B_02.01', 'active', 'B_02.01 c0020, c0040, c0050 must be reported'),
    'v22912_m': ('dpm', 'B_02.01', 'active', 'B_02.01: if {c0020} = [eba_CO:x3] then {c0030} != empty'),
    'v22913_s': ('dpm', 'B_01.02', 'active', 'B_01.02: {B 01.02} >= 0'),
    'v23716_s': ('dpm', 'B_02.01', 'active', 'B_02.01: {c0050} >= 0'),
    'v8803_m': ('dpm', 'B_01.02', 'active', 'B_01.02: if (not (isnull ({c0110}))) then (not (isnull ({c0100}))) endif'),
    'v8804_m': ('dpm', 'B_01.02', 'active', 'B_01.02: if({c0040} != [eba_CT:x318] and {c0040} != [eba_CT:x317]) then (not (isnull ({c0110}))) endif'),
    'v8805_m': ('dpm', 'B_02.01', 'active', 'B_02.01: if({c0020} = [eba_CO:x3]) then (not (isnull ({c0030}))) endif'),
    'v8816_m': ('dpm', 'B_02.02', 'inactive', 'B_02.02: Deactivated in March 2025'),
    'v8817_m': ('dpm', 'B_05.01', 'inactive', 'B_05.01: Deactivated in March 2025'),
    'v8818_m': ('dpm', 'B_05.01', 'inactive', 'B_05.01: Deactivated in March 2025'),
    'v8821_m': ('dpm', 'B_05.01', 'inactive', 'B_05.01: Deactivated in March 2025'),
    'v8823_m': ('dpm', 'B_05.01', 'inactive', 'B_05.01: Deactivated in March 2025'),
    'v8824_m': ('dpm', 'B_05.01', 'inactive', 'B_05.01: Deactivated in March 2025'),
    'v8825_m': ('dpm', 'B_07.01', 'active', 'B_07.01: if {c0050} = [eba_ZZ:x959] or {c0050} = [eba_ZZ:x960] then (not (isnull ({c0060}))) endif'),
    'v8826_m': ('dpm', 'B_01.02', 'active', 'B_01.02: Checks LEI format'),
    'v8850_m': ('dpm', 'B_05.01', 'active', 'B_05.01 c0020 must be reported when the row is reported'),
    'v8851_m': ('dpm', 'B_05.01', 'active', 'B_05.01 c0050 must be reported when the row is reported'),
    'v8852_m': ('dpm', 'B_05.01', 'active', 'B_05.01 c0060 must be reported when the row is reported'),
    'v8853_m': ('dpm', 'B_05.01', 'active', 'B_05.01 c0070 must be reported when the row is reported'),
    'v8854_m': ('dpm', 'B_05.01', 'active', 'B_05.01 c0080 must be reported when the row is reported'),
    'v8855_m': ('dpm', 'B_05.01', 'active', 'B_05.01 c0110 must be reported when the row is reported'),
    'v8856_m': ('dpm', 'B_01.03', 'active', 'B_01.03 c0040 must be reported when the row is reported'),
    'v8857_m': ('dpm', 'B_01.03', 'active', 'B_01.03 c0030 must be reported when the row is reported'),
    'v8858_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0020 must be reported when the row is reported'),
    'v8859_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0030 must be reported when the row is reported'),
    'v8860_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0040 must be reported when the row is reported'),
    'v8861_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0050 must be reported when the row is reported'),
    'v8862_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0060 must be reported when the row is reported'),
    'v8863_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0070 must be reported when the row is reported'),
    'v8864_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0080 must be reported when the row is reported'),
    'v8865_m': ('dpm', 'B_01.02', 'active', 'B_01.02 c0090 must be reported when the row is reported'),
    'v8866_m': ('dpm', 'B_02.01', 'active', 'B_02.01 c0050 must be reported when the row is reported'),
    'v8867_m': ('dpm', 'B_02.01', 'active', 'B_02.01 c0040 must be reported when the row is reported'),
    'v8868_m': ('dpm', 'B_02.01', 'active', 'B_02.01 c0020 must be reported when the row is reported'),
    'v8869_m': ('dpm', 'B_02.02', 'active', 'B_02.02 c0040 must be reported when the row is reported'),
    'v8870_m': ('dpm', 'B_02.02', 'active', 'B_02.02 c0070 must be reported when the row is reported'),
    'v8871_m': ('dpm', 'B_02.02', 'active', 'B_02.02 c0080 must be reported when the row is reported'),
    'v8872_m': ('dpm', 'B_01.01', 'active', 'B_01.01 c0020 must be reported when the row is reported'),
    'v8873_m': ('dpm', 'B_01.01', 'active', 'B_01.01 c0030 must be reported when the row is reported'),
    'v8874_m': ('dpm', 'B_01.01', 'active', 'B_01.01 c0040 must be reported when the row is reported'),
    'v8875_m': ('dpm', 'B_01.01', 'active', 'B_01.01 c0050 must be reported when the row is reported'),
    'v8876_m': ('dpm', 'B_01.01', 'active', 'B_01.01 c0060 must be reported when the row is reported'),
    'v8877_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0020 must be reported when the row is reported'),
    'v8878_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0030 must be reported when the row is reported'),
    'v8879_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0050 must be reported when the row is reported'),
    'v8880_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0070 must be reported when the row is reported'),
    'v8881_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0080 must be reported when the row is reported'),
    'v8882_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0090 must be reported when the row is reported'),
    'v8883_m': ('dpm', 'B_06.01', 'active', 'B_06.01 c0100 must be reported when the row is reported'),
    'v8884_m': ('dpm', 'B_07.01', 'active', 'B_07.01 c0050 must be reported when the row is reported'),
    'v8885_m': ('dpm', 'B_07.01', 'active', 'B_07.01 c0070 must be reported when the row is reported'),
    'v8886_m': ('dpm', 'B_07.01', 'active', 'B_07.01 c0080 must be reported when the row is reported'),
    'v8887_m': ('dpm', 'B_07.01', 'inactive', 'B_07.01 c0090 must be reported when the row is reported'),
    'v88889_m': ('dpm', 'B_07.01', 'active', 'B_07.01 c0110 must be reported when the row is reported'),
    'v8888_m': ('dpm', 'B_07.01', 'active', 'B_07.01 c0100 must be reported when the row is reported'),
    'v8890_m': ('dpm', 'B_01.01', 'active', 'B_01.01: This VR checks the format of column 0010 (LEI code)'),
    'v8891_m': ('dpm', 'B_01.02', 'active', 'B_01.02: This VR checks the format of column 0010 (LEI code)'),
    'v8892_m': ('dpm', 'B_01.03', 'active', 'B_01.03: This VR checks the format of column 0020 (LEI code)'),
    'v8893_m': ('dpm', 'B_02.02', 'inactive', 'B_02.02: Deactivated in March 2025'),
    'v8894_m': ('dpm', 'B_03.01', 'inactive', 'B_03.01: Deactivated in March 2025'),
    'v8895_m': ('dpm', 'B_03.03', 'inactive', 'B_03.03: Deactivated in March 2025'),
    'v8896_m': ('dpm', 'B_04.01', 'inactive', 'B_04.01: Deactivated in March 2025'),
    'v8897_m': ('dpm', 'B_06.01', 'inactive', 'B_06.01: Deactivated in March 2025'),
    'VR_2': ('business', 'B_01.01', 'active', 'LEI code validity: B_01.01 c0010 – LEI code needs to be a valid one according to the GLEIF database'),
    'VR_12': ('business', 'B_01.02', 'active', 'LEI code validity: B_01.02 c0010 – LEI code needs to be a valid one according to the GLEIF database'),
    'VR_16': ('business', 'B_01.02', 'active', 'Country Code validity: B_01.02 c0030 – Code needs to be a valid one according to the GLEIF database'),
    'VR_23': ('business', 'B_01.02', 'active', 'LEI code validity: B_01.02 c0060 – LEI code needs to be a valid one according to the GLEIF database'),
    'VR_71': ('business', 'B_05.01', 'active', "LEI code validity: B_05.01 c0010 – LEI code neeeds to be a valid one according to the GLEIF database (when b_05_01_c0020 = 'LEI')"),
    'VR_72': ('business', 'B_05.01', 'active', "EUID code validity: B_05.01 c0010 – EUID code needs to be a valid one according to the BRIS (when b_05_01_c0020 = 'EUID')"),
    'VR_77': ('business', 'B_05.01', 'active', "LEI code validity: B_05.01 c0030 – LEI code neeeds to be a valid one according to the GLEIF database (when b_05_01_c0040 = 'LEI')"),
    'VR_78': ('business', 'B_05.01', 'active', "EUID code validity: B_05.01 c0030 – EUID code needs to be a valid one according to the BRIS (when b_05_01_c0040 = 'EUID')"),
}
