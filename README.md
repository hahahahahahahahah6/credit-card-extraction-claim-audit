# Documentation claim auditor

An offline static auditor comparing documentation promises with recognized calls in Python source. It reports unsupported promises and contradictions, without executing project code. Requires Python 3.9 or newer; there are no runtime dependencies.

## Installation and usage

```sh
python3 -m pip install .
credit-card-extraction-claim-audit audit .
credit-card-extraction-claim-audit audit . --json --verbose --ignore build --ignore dist --fail-on medium
python3 -m credit_card_extraction_claim_audit audit .
credit-card-extraction-claim-audit --version
```

The optional repository argument defaults to the current directory. Ignore prefixes are relative paths and apply to entire subtrees. The default failure threshold is high; medium also fails on test-only evidence. Exit 0 means PASS at the selected threshold, 2 means findings at that threshold, and 1 means usage or I/O error. JSON includes verdict, findings (with rule, severity, message, and locations), and evidence paths. Verbose text also lists evidence paths.

## Matching rules

Only root README.md and Markdown files with a docs path component are checked. Fenced blocks using backticks or tildes with up to three leading spaces are excluded; inline code counts. Paragraphs split on blank lines. Matching lowercases text, expands contractions, replaces hyphens with spaces, and collapses whitespace. Exact boundary matches use longest phrases first, with alphabetical ties; denial spans are removed before positive matching. Each family yields at most one finding.

Source files are parsed with the standard AST library and never executed. Symlinks are excluded. Fixtures, docs, and examples are excluded from evidence; tests count separately. Invalid syntax yields no evidence. Imports and aliases are resolved within one module. Local function, method, and class definitions shadow route names. Assignments, annotated assignments, and context manager bindings shadow imported names. Bare imports and references do not count.

```text
credit card extraction
extract credit cards
extracts credit cards
extracting credit cards
extract credit card
extracts credit card
extracting credit card
credit card parsing
credit card parser
parse credit cards
parses credit cards
parse credit card
parses credit card
credit card scanning
credit card scanner
scan credit cards
scans credit cards
scan credit card
scans credit card
debit card extraction
extract debit cards
extracts debit cards
extracting debit cards
extract debit card
extracts debit card
extracting debit card
debit card parsing
debit card parser
parse debit cards
parses debit cards
parse debit card
parses debit card
payment card extraction
extract payment cards
extracts payment cards
extracting payment cards
extract payment card
extracts payment card
extracting payment card
payment card parsing
payment card parser
parse payment cards
parses payment cards
parse payment card
parses payment card
credit card data extraction
extract credit card data
credit card field extraction
credit card document extraction
extract credit card documents
no credit card extraction
does not extract credit cards
does not extract credit card
does not support credit card extraction
without credit card extraction
no debit card extraction
does not extract debit cards
does not extract debit card
does not support debit card extraction
without debit card extraction
no payment card extraction
does not extract payment cards
does not extract payment card
does not support payment card extraction
without payment card extraction
credit card extraction not supported
debit card extraction not supported
payment card extraction not supported
no credit card parser
does not parse credit cards
does not parse credit card
no credit card scanner
does not scan credit cards
does not scan credit card

Generic call names:
extract_credit_card, extract_credit_cards, parse_credit_card, parse_credit_cards, extract_debit_card, extract_debit_cards, parse_debit_card, parse_debit_cards, extract_payment_card, extract_payment_cards, parse_payment_card, parse_payment_cards, extract_credit_card_data, parse_credit_card_data, credit_card_extraction, credit_card_extractor, credit_card_parser, payment_card_extraction, extract_credit_card_info, parse_credit_card_info, credit_card_scan, credit_card_scanner, scan_credit_card, scan_credit_cards

Rules:
documented-credit-card-extraction-claim-false HIGH
(documented claim with evidence only in tests: MEDIUM)
documented-no-credit-card-extraction-claim-false HIGH

Azure pair: azure.ai.formrecognizer.DocumentAnalysisClient or
azure.ai.documentintelligence.DocumentIntelligenceClient construction plus
begin_analyze_document / begin_analyze_document_from_url with literal
prebuilt-creditCard as first argument or model_id keyword, in one module.
The SDK import gate is required. Attribute calls may use any base.
No mindee route and no veryfi route exist in this auditor.
```

A positive promise without any source files fails; a denial without source passes. Generic attribute calls count on any base; bare names require an imported recognized name. Arbitrary alias chains are not followed.

## Honest limitations

The following reference notes describe recognized spellings, exclusions, and ambiguity. They are fenced to avoid making promises about the auditor itself.

```text
- The bare phrases "credit card extraction" / "extract credit
  card" / "extract credit cards" are deliberately
  CREDITCARDEXTRACTION phrases: in document-tool docs they
  almost always name credit card extraction. But "credit card"
  can also name a payment method the tool merely accepts, a card
  image the tool merely displays, or a card the tool merely
  tokenizes for payment: a doc that means accepting, displaying,
  or tokenizing cards, not extracting fields from them, is a false
  positive; the tool flags the claim, only the code decides.
- "debit card extraction" / "extract debit card(s)" are
  deliberately phrases: the Azure model covers credit and debit
  cards alike. But "debit card" can also name a payment method
  the tool merely accepts: a doc that means accepting debit
  payments, not extracting fields from debit cards, is a false
  positive; the tool flags the claim, only the code decides.
- "payment card extraction" / "extract payment card(s)" are
  deliberately phrases: "payment card" can also name a stored
  payment method the tool merely charges, not a card document the
  tool extracts fields from. The tool flags the claim; only the
  code decides.
- "credit card scanning" / "scan credit card(s)" are
  deliberately phrases: "scanning" a card can mean merely
  photographing it or OCRing it into raw text, with no structured
  field extraction. The tool flags the claim; only the code
  decides.
- A generic `extract_credit_card(` / `parse_credit_card(`
  call can name a string parser for numbers the user typed in
  rather than a document extractor: the tool counts the call, the
  claim plus the code decide — and a subprocess call invoking an
  external CLI is NOT evidence by design, so a thin wrapper that
  only calls subprocess fails.
- Azure `begin_analyze_document` with model id
  "prebuilt-creditCard" counts as evidence: the model is GA in
  v4.0 (2024-11-30) and the tool detects the client call in
  source, not whether the call succeeds against a current API
  version. Say so in the README.
- Azure `begin_analyze_document` with "prebuilt-creditCard.us"
  is NOT detected: no such model id exists — the credit card
  model id has no ".us" suffix (unlike the US document models
  prebuilt-tax.us / prebuilt-payStub.us /
  prebuilt-healthInsuranceCard.us / prebuilt-check.us /
  prebuilt-bankStatement.us). Say so in the README.
- Azure `begin_analyze_document` with lowercase
  "prebuilt-creditcard" is NOT detected: model ids are matched
  case-sensitively and exactly — "prebuilt-creditCard" (capital
  C) counts, lowercase does not. (The Microsoft Learn
  language-support page lists shorthand labels in lowercase;
  those are table labels, not the model id.) Say so in the README.
- Mindee `parse` with ANY product is NOT detected: mindee has no
  credit card product in the Python SDK (4.22.0 wheel inspected
  2026-11-13), so no mindee parse can be a credit-card extraction
  operation. Say so in the README.
- Veryfi `process_any_document` / `process_any_document_url` are
  NOT detected: AnyDocs is generic configurable extraction, not a
  credit-card operation. Say so in the README.
- Veryfi `process_document` is NOT detected: it processes generic
  receipts and invoices. Only a credit-card method would count
  here, and none exists. Say so in the README.
- Veryfi `process_w2_document` / `process_w9_document` /
  `process_w8_document` are NOT detected: tax forms are a separate
  document type covered by the tax-form family. Say so in the
  README.
- Veryfi `process_check` / `process_check_url` /
  `process_check_with_remittance` /
  `process_check_with_remittance_url` are NOT detected: checks are
  a separate document type covered by the bank-check family. Say
  so in the README.
- Veryfi `process_bank_statement_document` /
  `process_bank_statement_document_url` are NOT detected: bank
  statements are a separate document type covered by the
  bank-statement family's domain. Say so in the README.
- Veryfi `process_bussines_card_document` /
  `process_bussines_card_document_url` are NOT detected: business
  cards are a separate document type covered by the
  business-card family. Say so in the README.
- Veryfi `get_business_cards` / `get_business_card` /
  `delete_business_card` are NOT detected: retrieval and
  management, not extraction. Say so in the README.
- Veryfi `classify_document` is NOT detected: classification, not
  extraction. Say so in the README.
- Azure `begin_analyze_document` with "prebuilt-invoice" /
  "prebuilt-receipt" / "prebuilt-layout" / "prebuilt-idDocument" /
  "prebuilt-check.us" / "prebuilt-tax.us" /
  "prebuilt-bankStatement.us" / "prebuilt-payStub.us" /
  "prebuilt-healthInsuranceCard.us" / "prebuilt-businessCard" is
  NOT detected, for the same reason: invoices, receipts, layouts,
  ID documents, checks, tax forms, bank statements, pay stubs,
  health insurance cards, and business cards are separate
  document types covered by their own families. Say so in the
  README.
- Mindee `parse` with InvoiceV4 / ReceiptV5 / PassportV1 /
  FinancialDocumentV1 / BankCheckV1 / BankAccountDetailsV2 /
  PayslipV2 / PayslipV3 / HealthcareCardV1 / BusinessCardV1 /
  CustomV1 is NOT detected: those are other document types, and
  mindee has no credit card product at all. Say so in the README.
- Textract `analyze_document` / `analyze_expense` /
  `start_document_analysis` / `get_expense_analysis` are NOT
  detected: generic document and expense analysis are not
  credit card extraction, and Textract has no credit card
  operation. Say so in the README.
- A hand-rolled extraction from OCR text (`re.search` /
  `re.findall` on extracted text plus manual field assembly, no
  listed call) is NOT detected: the tool requires a listed call.
  Say so in the README.
- The mindee CLI, the veryfi CLI, and any other external credit
  card tool invoked through subprocess are NOT detected:
  subprocess calls invoking an external CLI are NOT evidence by
  design. Say so in the README.
- Azure Document Intelligence, Mindee, and Veryfi are cloud APIs:
  the tool detects the client call in source, not whether
  credentials are configured or the call succeeds. Say so in the
  README.
- "extract card number" / "extract expiration date" / "extract
  issuing bank" claims are NOT in the phrase lists: card numbers,
  expiration dates, and issuing banks are card data points, not
  credit-card document extraction claims on their own. Say so in
  the README.
- Invoice extraction claims ("extract invoices", "invoice
  extraction"), receipt extraction claims ("extract receipts",
  "receipt extraction"), ID document extraction claims ("extract
  passports", "passport extraction"), bank check extraction claims
  ("extract bank checks", "check extraction"), bank statement
  extraction claims ("extract bank statements", "statement
  extraction"), tax form extraction claims ("extract tax forms",
  "extract w2 forms", "1099 extraction"), pay stub extraction
  claims ("extract pay stubs", "payslip extraction"), health
  insurance card extraction claims ("extract health insurance
  cards", "health insurance card extraction"), and business card
  extraction claims ("extract business cards", "business card
  extraction") are NOT in the phrase lists: this family covers
  credit cards only. Say so in the README.
- Payment processing claims ("accept credit cards", "process
  credit card payments", "charge credit cards") are NOT in the
  phrase lists: accepting or charging cards is not extracting
  fields from them. Say so in the README.
- As with every family: static pattern matching, not semantic
  judgement; dead code counts; alias chains the tracer cannot follow
  are missed; exact phrases only, not semantics; denial handling
  depends on the denial phrase list; each route must sit in a single
  module.


Additional exclusions: plain text via pdfplumber, fitz, pypdf, PyPDF2,
pdfminer; OCR via pytesseract; CSV/spreadsheets via pandas; tables via
camelot, tabula, pdfplumber, or fitz. Strings, comments, bare references,
invalid syntax and split-module pairs provide no evidence.
The non-existent veryfi process_credit_card_document and
process_credit_card_document_url methods provide no evidence.
```

## Differentiation

This checks documentation against a small explicit call vocabulary. It does not validate SDK behavior, returned fields, service availability, or credentials. Adjacent document types, OCR, table tools, and payment processing have different purposes. Static matches can include dead code and miss custom implementations.

## Development

```sh
python3 -m unittest discover
python3 -m venv .venv
.venv/bin/python3 -m pip install build
.venv/bin/python3 -m build
```

Both distributions include the tests. The tool uses only the standard library, makes no network requests, and writes only to standard output or standard error.
