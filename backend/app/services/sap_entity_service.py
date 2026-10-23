import re
from typing import Dict, Any, Optional, List

# Curated reference registry of verified SAP BRIM & S/4HANA technical entities
SAP_TECHNICAL_ENTITIES: Dict[str, Dict[str, Any]] = {
    # SAP Convergent Invoicing (CI) T-Codes & Tables
    "/1fe/": {
        "name": "/1FE/ (Class Prefix)",
        "type": "tcode_prefix",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Standard generated transaction code and table prefix for Billable Item (BIT) Classes in SAP Convergent Invoicing.",
        "verified_objects": ["/1FE/BIT_CREATE", "/1FE/BIT_MONITOR", "/1FE/BIT_DISPLAY"]
    },
    "fpc1": {
        "name": "FPC1",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Create Invoicing Order / Individual Invoicing Run in Convergent Invoicing.",
        "standard_use": "Executes billing and invoicing for selected contract accounts or business partners."
    },
    "fpc2": {
        "name": "FPC2",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Mass Invoicing Run in Convergent Invoicing.",
        "standard_use": "Executes mass batch processing of billable items into invoicing documents."
    },
    "fpc0": {
        "name": "FPC0",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Display Invoicing Document in Convergent Invoicing.",
        "standard_use": "Inspects invoicing document headers, items, and linked billing documents."
    },
    "dfkkbict": {
        "name": "DFKKBICT",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Items: Control Data and Item Status Table.",
        "key_fields": ["MANDT", "BITCAT", "BITSTATUS", "SRCTYPE"]
    },
    "dfkkbict_it": {
        "name": "DFKKBICT_IT",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Item Main Items (IT) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "BITSTATUS", "VKONT", "GPART"]
    },
    "dfkkbict_py": {
        "name": "DFKKBICT_PY",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Item Payment Data (PY) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "PY_AMOUNT", "WAERS"]
    },
    "dfkkbict_tx": {
        "name": "DFKKBICT_TX",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Item Tax Data (TX) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "TAX_AMOUNT", "TAX_DATE"]
    },

    # SAP FI-CA (Contract Accounts Receivable and Payable)
    "fpcopara": {
        "name": "FPCOPARA",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Correspondence Run in FI-CA.",
        "standard_use": "Mass output processing for invoices, account statements, and dunning letters."
    },
    "fpe1": {
        "name": "FPE1",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Post Document in FI-CA.",
        "standard_use": "Manual posting of financial documents into contract accounts."
    },
    "fpe2": {
        "name": "FPE2",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Change Document in FI-CA.",
        "standard_use": "Modifies open item line item attributes (e.g. payment terms, dunning locks)."
    },
    "fpe3": {
        "name": "FPE3",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Display Document in FI-CA.",
        "standard_use": "Inspects document header (DFKKKO) and line items (DFKKOP)."
    },
    "fp05": {
        "name": "FP05",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Payment Lot Processing in FI-CA.",
        "standard_use": "Processes incoming customer bank payments and clearing of open items."
    },
    "fpva": {
        "name": "FPVA",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Dunning Proposal Run in FI-CA.",
        "standard_use": "Evaluates overdue open items and proposes dunning levels."
    },
    "fpvb": {
        "name": "FPVB",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Dunning Activity Run in FI-CA.",
        "standard_use": "Executes dunning actions, generates dunning fees, interest, and letters."
    },
    "dfkkko": {
        "name": "DFKKKO",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Document Header Table.",
        "key_fields": ["MANDT", "OPBEL", "FIKEY", "BLDAT", "BUDAT"]
    },
    "dfkkop": {
        "name": "DFKKOP",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Contract Account Document: Line Item Table (Open Items).",
        "key_fields": ["MANDT", "OPBEL", "OPUPK", "OPUPW", "OPUPZ", "VKONT", "GPART", "BETRW"]
    },
    "dfkkopk": {
        "name": "DFKKOPK",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Document: General Ledger Items.",
        "key_fields": ["MANDT", "OPBEL", "OPUPK", "HKONT", "BETRW"]
    },

    # Master Data Entities
    "but000": {
        "name": "BUT000",
        "type": "table",
        "component": "SAP Master Data (BP)",
        "description": "Business Partner General Data Table (Central Header).",
        "key_fields": ["CLIENT", "PARTNER", "TYPE", "NAME_FIRST", "NAME_LAST"]
    },
    "fkkvkp": {
        "name": "FKKVKP",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "Contract Account Header and Partner-Specific Data.",
        "key_fields": ["MANDT", "VKONT", "GPART"]
    },

    # Core ERP Transactions
    "me21n": {
        "name": "ME21N",
        "type": "tcode",
        "component": "SAP MM",
        "description": "Create Purchase Order.",
        "standard_use": "Purchasing transaction for procurement orders in SAP ERP / S/4HANA."
    },
    "migo": {
        "name": "MIGO",
        "type": "tcode",
        "component": "SAP MM",
        "description": "Goods Movement (Goods Receipt / Issue).",
        "standard_use": "Processes inventory movements and posts warehouse receipts."
    },
    "miro": {
        "name": "MIRO",
        "type": "tcode",
        "component": "SAP MM / FI",
        "description": "Enter Incoming Invoice (Logistics Invoice Verification).",
        "standard_use": "Performs 3-Way Match validation against Purchase Order and Goods Receipt."
    },
    "sm30": {
        "name": "SM30",
        "type": "tcode",
        "component": "SAP Basis / Customizing",
        "description": "Call View Maintenance.",
        "standard_use": "Maintains configuration tables and views defined in ABAP Dictionary."
    },
    "se16": {
        "name": "SE16",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "Data Browser.",
        "standard_use": "Displays database table contents and records."
    },
    "se16n": {
        "name": "SE16N",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "General Table Display.",
        "standard_use": "Interactive browser for ABAP database tables."
    },
    "spro": {
        "name": "SPRO",
        "type": "tcode",
        "component": "SAP Customizing",
        "description": "Customizing - Edit Project / SAP Reference IMG.",
        "standard_use": "Central entry transaction for all SAP configuration and IMG paths."
    },
    # SAP BRIM CI & FI-CA Mass Execution & Diagnostics
    "fkkbix_bill_m": {
        "name": "FKKBIX_BILL_M",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Mass Billing Run in Convergent Invoicing.",
        "standard_use": "Aggregates billable items into billing documents."
    },
    "fkkbix_bill_s": {
        "name": "FKKBIX_BILL_S",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Single Account Billing Run in Convergent Invoicing.",
        "standard_use": "Executes single contract account billing simulation or update run."
    },
    "fkkbix_inv_m": {
        "name": "FKKBIX_INV_M",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Mass Invoicing Run in Convergent Invoicing.",
        "standard_use": "Executes batch invoicing creating legal invoicing documents and FI-CA postings."
    },
    "fkkinv_m": {
        "name": "FKKINV_M",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Mass Invoicing of Billing Documents.",
        "standard_use": "Processes invoicing orders into invoicing documents."
    },
    "fkkbix_bill_rev": {
        "name": "FKKBIX_BILL_REV",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Reverse Billing Document.",
        "standard_use": "Reverses CI billing documents and restores BITs to billable status."
    },
    "fkkinv_rev": {
        "name": "FKKINV_REV",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Reverse Invoicing Document.",
        "standard_use": "Reverses invoicing documents and creates reversal document in FI-CA."
    },
    "fkkbix_bit_exc": {
        "name": "FKKBIX_BIT_EXC",
        "type": "tcode",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Exception Handling for Billable Items.",
        "standard_use": "Manages excepted BITs and releases them for reprocessing."
    },
    "fpy1": {
        "name": "FPY1",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Automatic Payment Run in FI-CA.",
        "standard_use": "Mass payment program executing direct debits, bank transfers, and automated clearing."
    },
    "fp08": {
        "name": "FP08",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Reverse Document in FI-CA.",
        "standard_use": "Reverses posted FI-CA documents with reversal reason."
    },
    "fp07": {
        "name": "FP07",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Reset Clearing in FI-CA.",
        "standard_use": "Resets clearing status on cleared line items, reopening them."
    },
    "fpg1": {
        "name": "FPG1",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Close Reconciliation Key in FI-CA.",
        "standard_use": "Closes open FIKEY to prepare totals records for G/L transfer."
    },
    "fpg4": {
        "name": "FPG4",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Transfer Totals Records to General Ledger.",
        "standard_use": "Transfers FI-CA totals records from DFKKAK into General Ledger (ACDOCA/BSEG)."
    },
    "fpg0": {
        "name": "FPG0",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Display Reconciliation Key.",
        "standard_use": "Inspects status and totals records of FI-CA reconciliation key."
    },
    "fpo1": {
        "name": "FPO1",
        "type": "tcode",
        "component": "SAP FI-CA",
        "description": "Display Account Balance in FI-CA.",
        "standard_use": "Displays contract account balance, cleared items, and open items."
    },
    "crmd_order": {
        "name": "CRMD_ORDER",
        "type": "tcode",
        "component": "SAP SOM (CRM/S4)",
        "description": "Maintain Transaction / Provider Order / Subscription Contract.",
        "standard_use": "Order and contract maintenance transaction in SAP Subscription Order Management."
    },
    "slg1": {
        "name": "SLG1",
        "type": "tcode",
        "component": "SAP Basis / Application Log",
        "description": "Application Log: Display Logs.",
        "standard_use": "Displays application logs for objects such as CRM_ORDER, ODI, FKKBIX, and FI-CA."
    },
    "sm37": {
        "name": "SM37",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "Overview of Job Selection.",
        "standard_use": "Monitors background job status, execution logs, and spool outputs."
    },
    "sm58": {
        "name": "SM58",
        "type": "tcode",
        "component": "SAP Basis / RFC",
        "description": "Asynchronous RFC Error Log.",
        "standard_use": "Monitors transactional RFC calls (e.g. CC to CI charged item transfer)."
    },
    "smq1": {
        "name": "SMQ1",
        "type": "tcode",
        "component": "SAP Basis / qRFC",
        "description": "qRFC Monitor (Outbound Queue).",
        "standard_use": "Monitors and troubleshoots outbound queued RFC processing."
    },
    "smq2": {
        "name": "SMQ2",
        "type": "tcode",
        "component": "SAP Basis / qRFC",
        "description": "qRFC Monitor (Inbound Queue).",
        "standard_use": "Monitors and troubleshoots inbound queued RFC processing."
    },
    "sm12": {
        "name": "SM12",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "Display and Delete Lock Entries.",
        "standard_use": "Inspects enqueue database locks on contract accounts, orders, and tables."
    },
    "se93": {
        "name": "SE93",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "Maintain Transaction Codes.",
        "standard_use": "Displays transaction code attributes and linked programs."
    },
    "se11": {
        "name": "SE11",
        "type": "tcode",
        "component": "SAP Basis",
        "description": "ABAP Dictionary Maintenance.",
        "standard_use": "Inspects table structures, fields, and domain values."
    },
    # Verified Database Tables
    "dfkkbixbit0": {
        "name": "DFKKBIXBIT0",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Raw Billable Items Table.",
        "key_fields": ["MANDT", "BITNUMBER", "BITCAT", "BITSTATUS"]
    },
    "dfkkbixbit2": {
        "name": "DFKKBIXBIT2",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billable Items (Billable Status) Table.",
        "key_fields": ["MANDT", "BITNUMBER", "BITCAT", "BITSTATUS"]
    },
    "dfkkbixbit4": {
        "name": "DFKKBIXBIT4",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Billed Billable Items Table.",
        "key_fields": ["MANDT", "BITNUMBER", "BITCAT", "BITSTATUS"]
    },
    "dfkkinvdoc_h": {
        "name": "DFKKINVDOC_H",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Invoicing Document Header Table.",
        "key_fields": ["MANDT", "INVDOCNO", "GPART", "VKONT", "DATE_FROM"]
    },
    "dfkkinvdoc_i": {
        "name": "DFKKINVDOC_I",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Invoicing Document Items Table.",
        "key_fields": ["MANDT", "INVDOCNO", "INVDOCITEM", "BETRW"]
    },
    "dfkkinv_ord": {
        "name": "DFKKINV_ORD",
        "type": "table",
        "component": "SAP Convergent Invoicing (CI)",
        "description": "Invoicing Orders Trigger Table.",
        "key_fields": ["MANDT", "VKONT", "GPART", "SRCDOCTYPE", "SRCDOCNO"]
    },
    "dfkkak": {
        "name": "DFKKAK",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Reconciliation Key Header Table.",
        "key_fields": ["MANDT", "FIKEY", "FIKST", "BUDAT"]
    },
    "dfkksum": {
        "name": "DFKKSUM",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Totals Records for G/L Transfer Table.",
        "key_fields": ["MANDT", "FIKEY", "BUKRS", "HKONT", "BETRW"]
    },
    "fkkmako": {
        "name": "FKKMAKO",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Dunning History Header Table.",
        "key_fields": ["MANDT", "LAUFD", "LAUFI", "GPART", "VKONT"]
    },
    "fkkmaze": {
        "name": "FKKMAZE",
        "type": "table",
        "component": "SAP FI-CA",
        "description": "FI-CA Dunning History Line Items Table.",
        "key_fields": ["MANDT", "LAUFD", "LAUFI", "GPART", "VKONT", "OPBEL"]
    },
    "acdoca": {
        "name": "ACDOCA",
        "type": "table",
        "component": "SAP S/4HANA Finance",
        "description": "Universal Journal Entry Line Items Table.",
        "key_fields": ["RCLNT", "RLDNR", "RBUKRS", "GJAHR", "BELNR", "DOCLN"]
    },
    "bseg": {
        "name": "BSEG",
        "type": "table",
        "component": "SAP Financial Accounting (FI)",
        "description": "Accounting Document Segment Table.",
        "key_fields": ["MANDT", "BUKRS", "BELNR", "GJAHR", "BUZEI"]
    },
    "bkpf": {
        "name": "BKPF",
        "type": "table",
        "component": "SAP Financial Accounting (FI)",
        "description": "Accounting Document Header Table.",
        "key_fields": ["MANDT", "BUKRS", "BELNR", "GJAHR"]
    },
    "crmd_orderadm_h": {
        "name": "CRMD_ORDERADM_H",
        "type": "table",
        "component": "SAP SOM (CRM)",
        "description": "Business Transaction Header Table.",
        "key_fields": ["CLIENT", "GUID", "OBJECT_ID", "PROCESS_TYPE"]
    },
    "crmd_orderadm_i": {
        "name": "CRMD_ORDERADM_I",
        "type": "table",
        "component": "SAP SOM (CRM)",
        "description": "Business Transaction Item Table.",
        "key_fields": ["CLIENT", "GUID", "HEADER", "NUMBER_INT"]
    }
}


class SAPEntityService:
    """Provides entity lookups for documented SAP T-codes, tables, and BRIM components."""

    @staticmethod
    def lookup_entity(identifier: str) -> Optional[Dict[str, Any]]:
        clean_id = identifier.lower().strip()
        # Direct match
        if clean_id in SAP_TECHNICAL_ENTITIES:
            return SAP_TECHNICAL_ENTITIES[clean_id]
        # Prefix match (e.g. for /1FE/ classes)
        for key, entry in SAP_TECHNICAL_ENTITIES.items():
            if clean_id.startswith(key):
                return entry
        return None

    @staticmethod
    def is_known_sap_identifier(identifier: str) -> bool:
        clean_id = identifier.lower().strip()
        if clean_id in SAP_TECHNICAL_ENTITIES:
            return True
        for key in SAP_TECHNICAL_ENTITIES:
            if clean_id.startswith(key):
                return True
        return False


sap_entity_service = SAPEntityService()
