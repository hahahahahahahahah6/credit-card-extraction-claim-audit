import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from credit_card_extraction_claim_audit import phrases
from credit_card_extraction_claim_audit.audit import audit, source_evidence, match_phrases
from credit_card_extraction_claim_audit.__main__ import main

EXPECTED_POSITIVE = ('credit card extraction', 'extract credit cards', 'extracts credit cards', 'extracting credit cards', 'extract credit card', 'extracts credit card', 'extracting credit card', 'credit card parsing', 'credit card parser', 'parse credit cards', 'parses credit cards', 'parse credit card', 'parses credit card', 'credit card scanning', 'credit card scanner', 'scan credit cards', 'scans credit cards', 'scan credit card', 'scans credit card', 'debit card extraction', 'extract debit cards', 'extracts debit cards', 'extracting debit cards', 'extract debit card', 'extracts debit card', 'extracting debit card', 'debit card parsing', 'debit card parser', 'parse debit cards', 'parses debit cards', 'parse debit card', 'parses debit card', 'payment card extraction', 'extract payment cards', 'extracts payment cards', 'extracting payment cards', 'extract payment card', 'extracts payment card', 'extracting payment card', 'payment card parsing', 'payment card parser', 'parse payment cards', 'parses payment cards', 'parse payment card', 'parses payment card', 'credit card data extraction', 'extract credit card data', 'credit card field extraction', 'credit card document extraction', 'extract credit card documents')
EXPECTED_NEGATIVE = ('no credit card extraction', 'does not extract credit cards', 'does not extract credit card', 'does not support credit card extraction', 'without credit card extraction', 'no debit card extraction', 'does not extract debit cards', 'does not extract debit card', 'does not support debit card extraction', 'without debit card extraction', 'no payment card extraction', 'does not extract payment cards', 'does not extract payment card', 'does not support payment card extraction', 'without payment card extraction', 'credit card extraction not supported', 'debit card extraction not supported', 'payment card extraction not supported', 'no credit card parser', 'does not parse credit cards', 'does not parse credit card', 'no credit card scanner', 'does not scan credit cards', 'does not scan credit card')
EXPECTED_GENERIC = ('extract_credit_card', 'extract_credit_cards', 'parse_credit_card', 'parse_credit_cards', 'extract_debit_card', 'extract_debit_cards', 'parse_debit_card', 'parse_debit_cards', 'extract_payment_card', 'extract_payment_cards', 'parse_payment_card', 'parse_payment_cards', 'extract_credit_card_data', 'parse_credit_card_data', 'credit_card_extraction', 'credit_card_extractor', 'credit_card_parser', 'payment_card_extraction', 'extract_credit_card_info', 'parse_credit_card_info', 'credit_card_scan', 'credit_card_scanner', 'scan_credit_card', 'scan_credit_cards')

AZURE = 'from azure.ai.formrecognizer import DocumentAnalysisClient\nc = DocumentAnalysisClient()\nc.begin_analyze_document("prebuilt-creditCard", data)\n'


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['audit', str(self.root), *args])
        return code, output.getvalue()

    def claim(self):
        self.write('README.md', 'We extract credit cards.')

    def test_phrase_oracle(self):
        tree = ast.parse(Path(phrases.__file__).read_text())
        values = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)}
        self.assertEqual(values['CREDITCARDEXTRACTION'], EXPECTED_POSITIVE)
        self.assertEqual(values['NOCREDITCARDEXTRACTION'], EXPECTED_NEGATIVE)
        self.assertEqual(values['GENERIC_NAMES'], EXPECTED_GENERIC)
        self.assertEqual((len(EXPECTED_POSITIVE), len(EXPECTED_NEGATIVE), len(EXPECTED_GENERIC)), (50, 24, 24))
        self.assertEqual(len(set(EXPECTED_GENERIC)), 24)

    def test_good_pass(self):
        self.claim()
        self.write('app.py', AZURE)
        self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_bad_high_exact(self):
        self.claim()
        self.write('app.py', 'print("hello")')
        code, output = self.run_cli('--json')
        result = json.loads(output)
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'], [{'rule': 'documented-credit-card-extraction-claim-false', 'severity': 'HIGH', 'message': 'Documented capability has no production evidence.', 'locations': ['README.md']}])

    def test_test_only_threshold(self):
        self.claim()
        self.write('tests/route.py', AZURE)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
        self.assertEqual(self.run_cli()[0], 0)
        code, output = self.run_cli('--fail-on', 'medium', '--json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['verdict'], 'FAIL')

    def test_denial_high_exact(self):
        self.write('README.md', 'Does not extract credit cards.')
        self.write('app.py', AZURE)
        code, output = self.run_cli('--json')
        self.assertEqual(code, 2)
        finding = json.loads(output)['findings'][0]
        self.assertEqual(finding['rule'], 'documented-no-credit-card-extraction-claim-false')
        self.assertEqual(finding['severity'], 'HIGH')
        self.assertTrue(finding['message'])
        self.assertEqual(len(audit(self.root)['findings']), 1)

    def test_no_claim(self):
        self.write('README.md', 'An ordinary project.')
        self.write('app.py', AZURE)
        self.assertEqual(self.run_cli()[0], 0)

    def test_no_source_positive(self):
        self.claim()
        self.assertEqual(self.run_cli()[0], 2)

    def test_no_source_denial(self):
        self.write('README.md', 'No credit card extraction.')
        self.assertEqual(self.run_cli()[0], 0)

    def test_fences(self):
        for marker in ('```', '~~~', '   ````', '  ~~~~'):
            with self.subTest(marker=marker):
                self.write('README.md', marker + 'text\nextract credit cards\n' + marker.strip() + '\nNeutral prose.')
                self.assertEqual(self.run_cli()[0], 0)

    def test_fence_short_close_does_not_end_block(self):
        self.write('README.md', '````\n```\nextract credit cards\n````')
        self.assertEqual(self.run_cli()[0], 0)

    def test_inline_counts(self):
        self.write('README.md', 'Supports `extract credit cards`.')
        self.assertEqual(self.run_cli()[0], 2)

    def test_doc_scope(self):
        self.write('other.md', 'extract credit cards')
        self.write('nested/README.md', 'extract credit cards')
        self.assertEqual(self.run_cli()[0], 0)
        self.write('nested/docs/deeper/a.md', 'extract credit cards')
        self.assertEqual(audit(self.root)['findings'][0]['locations'], ['nested/docs/deeper/a.md'])

    def test_paragraph_boundaries(self):
        self.write('README.md', 'extract credit\n\ncards')
        self.assertEqual(self.run_cli()[0], 0)
        self.write('README.md', 'EXTRACT-CREDIT\nCARDS')
        self.assertEqual(self.run_cli()[0], 2)

    def test_word_boundaries(self):
        self.assertEqual(match_phrases('reextract credit cardsuffix'), ([], []))

    def test_contractions(self):
        self.assertEqual(match_phrases("doesn't extract credit cards"), (['does not extract credit cards'], []))

    def test_longest_first(self):
        self.assertEqual(match_phrases('extract credit card documents'), ([], ['extract credit card documents']))

    def test_one_finding_per_family(self):
        self.write('README.md', 'extract credit cards\n\ncredit card extraction')
        self.write('docs/a.md', 'scan credit cards')
        self.assertEqual(len(audit(self.root)['findings']), 1)

    def test_split_modules(self):
        self.claim()
        self.write('a.py', 'from azure.ai.formrecognizer import DocumentAnalysisClient\nc=DocumentAnalysisClient()')
        self.write('b.py', 'c.begin_analyze_document("prebuilt-creditCard", data)')
        self.assertEqual(self.run_cli()[0], 2)

    def test_symlink_file(self):
        self.claim()
        outside = self.root.parent / (self.root.name + '-outside.py')
        outside.write_text(AZURE)
        self.addCleanup(outside.unlink)
        (self.root / 'route.py').symlink_to(outside)
        self.assertEqual(self.run_cli()[0], 2)

    def test_symlink_directory(self):
        self.claim()
        self.write('excluded/route.py', AZURE)
        (self.root / 'linked').symlink_to(self.root / 'excluded', target_is_directory=True)
        self.assertEqual(self.run_cli('--ignore', 'excluded')[0], 2)

    def test_symlink_docs(self):
        self.write('other.md', 'extract credit cards')
        (self.root / 'README.md').symlink_to(self.root / 'other.md')
        self.assertEqual(self.run_cli()[0], 0)

    def test_ignore_prefixes(self):
        self.claim()
        self.write('src/app.py', AZURE)
        self.write('src2/app.py', AZURE)
        self.assertEqual(self.run_cli('--ignore', 'src')[0], 0)
        self.assertEqual(self.run_cli('--ignore', 'src', '--ignore', 'src2')[0], 2)
        self.assertEqual(self.run_cli('--ignore', 'README.md')[0], 0)

    def test_json_and_verbose(self):
        self.claim()
        self.write('app.py', AZURE)
        code, output = self.run_cli('--json', '--verbose')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['evidence']['production'], ['app.py'])
        self.assertIn('app.py', self.run_cli('--verbose')[1])

    def test_bad_path(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['audit', str(self.root / 'missing')]), 1)

    def test_usage_errors(self):
        for args in ([], ['wrong'], ['audit', '--fail-on', 'HIGH'], ['audit', '--ignore'], ['audit', '.', '--ignore', 'x', 'y']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main(args)
            self.assertEqual(caught.exception.code, 1)

    def test_version(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            main(['--version'])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(output.getvalue(), '0.1.0\n')

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, '-m', 'credit_card_extraction_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, '0.1.0\n'))

    def test_console_entrypoint_contract(self):
        config = (Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text()
        self.assertIn('credit-card-extraction-claim-audit = "credit_card_extraction_claim_audit.__main__:main"', config)

    def test_azure_api_version_not_validated(self):
        self.assertTrue(source_evidence(AZURE.replace('DocumentAnalysisClient()', 'DocumentAnalysisClient(api_version="old")')))

    def test_dead_code_counts(self):
        self.assertTrue(source_evidence('if False:\n    sdk.extract_credit_card(data)'))

    def test_generic_bare_string_parser_not_evidence(self):
        self.assertFalse(source_evidence('parse_credit_card("already extracted text")'))

    def test_generic_imported_string_parser_limitation(self):
        self.assertTrue(source_evidence('from sdk import parse_credit_card\nparse_credit_card("already extracted text")'))


def evidence_test(source, expected):
    def test(self):
        self.assertEqual(source_evidence(source), expected, source)
    return test


# All names are tested independently, both attribute and imported aliases.
for index, name in enumerate(EXPECTED_GENERIC):
    setattr(AuditTests, 'test_generic_attribute_%02d' % index, evidence_test('x.' + name + '(data)', True))
    setattr(AuditTests, 'test_generic_import_%02d' % index, evidence_test('from sdk import ' + name + ' as route\nroute(data)', True))
    setattr(AuditTests, 'test_generic_bare_%02d' % index, evidence_test(name + '(data)', False))
    setattr(AuditTests, 'test_generic_shadow_%02d' % index, evidence_test('class C:\n def ' + name + '(self): pass\nx.' + name + '(data)', False))

for index, phrase in enumerate(EXPECTED_POSITIVE):
    def test_positive(self, phrase=phrase):
        negative, positive = match_phrases(phrase)
        self.assertEqual((negative, positive), ([], [phrase]))
    setattr(AuditTests, 'test_positive_phrase_%02d' % index, test_positive)
for index, phrase in enumerate(EXPECTED_NEGATIVE):
    def test_negative(self, phrase=phrase):
        self.assertEqual(match_phrases(phrase), ([phrase], []))
    setattr(AuditTests, 'test_negative_phrase_%02d' % index, test_negative)

azure_forms = [
    AZURE,
    'from azure.ai.documentintelligence import DocumentIntelligenceClient as D\nc=D()\nc.begin_analyze_document_from_url("prebuilt-creditCard", url)',
    'import azure.ai.formrecognizer as fr\nc=fr.DocumentAnalysisClient()\nc.begin_analyze_document(model_id="prebuilt-creditCard", body=data)',
    'import azure.ai.documentintelligence\nc=azure.ai.documentintelligence.DocumentIntelligenceClient()\nc.begin_analyze_document("prebuilt-creditCard", data)',
    'from azure.ai import formrecognizer as fr\nc=fr.DocumentAnalysisClient()\nc.begin_analyze_document_from_url(model_id="prebuilt-creditCard", document_url=url)',
    'from azure.ai.documentintelligence import DocumentIntelligenceClient\nc=DocumentIntelligenceClient()\nc.begin_analyze_document(model_id="prebuilt-creditCard", body=data)',
]
for index, source in enumerate(azure_forms):
    setattr(AuditTests, 'test_azure_route_%02d' % index, evidence_test(source, True))

wrong_models = ('prebuilt-invoice', 'prebuilt-receipt', 'prebuilt-layout', 'prebuilt-read', 'prebuilt-idDocument', 'prebuilt-check.us', 'prebuilt-tax.us', 'prebuilt-bankStatement.us', 'prebuilt-payStub.us', 'prebuilt-healthInsuranceCard.us', 'prebuilt-businessCard', 'prebuilt-creditCard.us', 'prebuilt-creditcard', 'other')
for index, model in enumerate(wrong_models):
    setattr(AuditTests, 'test_azure_wrong_model_%02d' % index, evidence_test(AZURE.replace('prebuilt-creditCard', model), False))

mindee_products = ('InvoiceV4', 'ReceiptV5', 'PassportV1', 'FinancialDocumentV1', 'BankCheckV1', 'BankAccountDetailsV2', 'PayslipV2', 'PayslipV3', 'HealthcareCardV1', 'BusinessCardV1', 'CustomV1', 'CreditCardV1', 'Anything')
for index, product in enumerate(mindee_products):
    source = 'from mindee import Client, product\nc=Client()\nc.parse(product.' + product + ', data)'
    setattr(AuditTests, 'test_mindee_not_evidence_%02d' % index, evidence_test(source, False))

veryfi_methods = ('process_document', 'process_document_url', 'process_any_document', 'process_any_document_url', 'process_check', 'process_check_url', 'process_check_with_remittance', 'process_check_with_remittance_url', 'process_bank_statement_document', 'process_bank_statement_document_url', 'process_w2_document', 'process_w9_document', 'process_w8_document', 'process_bussines_card_document', 'process_bussines_card_document_url', 'classify_document', 'get_business_cards', 'get_business_card', 'delete_business_card', 'process_credit_card_document', 'process_credit_card_document_url', 'anything')
for index, method in enumerate(veryfi_methods):
    setattr(AuditTests, 'test_veryfi_not_evidence_%02d' % index, evidence_test('from veryfi import Client\nc=Client()\nc.' + method + '(data)', False))

non_evidence = [
    'import mindee', 'import veryfi', 'import azure.ai.formrecognizer',
    'from mindee import Client\nc=Client()',
    'from veryfi import Client\nc=Client()',
    'from azure.ai.formrecognizer import DocumentAnalysisClient\nc=DocumentAnalysisClient()',
    'c.begin_analyze_document("prebuilt-creditCard", data)',
    'import azure\nc=azure.DocumentAnalysisClient()\nc.begin_analyze_document("prebuilt-creditCard", data)',
    'from azure.ai.formrecognizer import DocumentAnalysisClient\nc=DocumentAnalysisClient()\nc.begin_analyze_document(model_id=model)',
    'import boto3\nc=boto3.client("textract")\nc.analyze_document(data)',
    'c.analyze_expense(data)', 'c.start_document_analysis(data)', 'c.get_expense_analysis(data)',
    'pdfplumber.extract_text(data)', 'fitz.extract_text(data)', 'pypdf.extract_text(data)', 'PyPDF2.extract_text(data)', 'pdfminer.extract_text(data)',
    'pytesseract.image_to_string(data)', 'pandas.read_csv(data)', 'pandas.read_excel(data)',
    'camelot.read_pdf(data)', 'tabula.read_pdf(data)', 'tabula.convert_into(data)',
    'pdfplumber.extract_table(data)', 'pdfplumber.extract_tables(data)', 'pdfplumber.find_table(data)', 'pdfplumber.find_tables(data)', 'fitz.find_tables(data)',
    'import re\ntext=ocr(data)\nfields={"number": re.search(r"[0-9]+", text)}',
    'import re\nfields=re.findall(r"[0-9]+", text)',
    'import subprocess\nsubprocess.run(["mindee", "parse", "data"])',
    'import subprocess\nsubprocess.run(["veryfi", "parse", "data"])',
    'import subprocess\nsubprocess.run(["credit-card-cli", "data"])',
    '"x.extract_credit_card(data)"\n# x.extract_credit_card(data)',
    'from sdk import extract_credit_card\nextract_credit_card',
    'x.extract_credit_card(data)\ninvalid =',
    'from sdk import extract_credit_card as route\ndef route(): pass\nroute(data)',
    'from sdk import extract_credit_card as route\nroute = other\nroute(data)',
    'from sdk import extract_credit_card as route\nroute: object = other\nroute(data)',
    'from sdk import extract_credit_card as route\nwith manager() as route:\n route(data)',
    'from sdk import extract_credit_card as route\nasync def f():\n async with manager() as route:\n  route(data)',
    'from sdk import extract_credit_card as route\nwith manager() as (route, other):\n route(data)',
    'from sdk import extract_credit_card as route\nclass extract_credit_card: pass\nroute(data)',
    AZURE + '\ndef DocumentAnalysisClient(): pass',
    AZURE + '\nclass Fake:\n def begin_analyze_document(self): pass',
    AZURE.replace('c = DocumentAnalysisClient()', 'DocumentAnalysisClient = fake\nc = DocumentAnalysisClient()'),
    'import azure.ai.formrecognizer as fr\nwith manager() as fr:\n c=fr.DocumentAnalysisClient()\nc.begin_analyze_document("prebuilt-creditCard", data)',
]
for index, source in enumerate(non_evidence):
    setattr(AuditTests, 'test_not_evidence_%02d' % index, evidence_test(source, False))

for index, path in enumerate(('fixtures/a.py', 'docs/a.py', 'examples/a.py', 'nested/fixtures/a.py')):
    def test_excluded(self, path=path):
        self.claim()
        self.write(path, AZURE)
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(audit(self.root)['evidence']['tests'])
    setattr(AuditTests, 'test_excluded_path_%02d' % index, test_excluded)
for index, path in enumerate(('tests/a.py', 'test_app.py', 'app_test.py', 'nested/tests/a.py')):
    def test_test_path(self, path=path):
        self.claim()
        self.write(path, AZURE)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
    setattr(AuditTests, 'test_test_path_%02d' % index, test_test_path)

if __name__ == '__main__':
    unittest.main()
