import unittest
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.main import app
from app.resume import extract_resume, MAX_UPLOAD

TEXT = 'Candidate built Python APIs and evaluated retrieval systems with labeled queries.'


def docx(xml=None):
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', xml or (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Candidate built Python APIs</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Evaluated retrieval systems with labeled queries.</w:t>'
            '</w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'))
    return out.getvalue()


def pdf(blank=False, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if not blank:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 50 700 Td ({TEXT}) Tj ET'.encode())
        page[NameObject('/Contents')] = stream
    if encrypted:
        writer.encrypt('test-password')
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


class ResumeTests(unittest.TestCase):
    def test_pdf_and_docx_extract_actual_text(self):
        self.assertIn(TEXT, extract_resume(pdf(), 'pdf'))
        result = extract_resume(docx(), 'docx')
        self.assertIn('Python APIs\nEvaluated retrieval', result)

    def test_invalid_scanned_encrypted_and_oversized_files(self):
        for data, kind in [(b'bad', 'pdf'), (pdf(blank=True), 'pdf'),
                           (pdf(encrypted=True), 'pdf'), (b'x' * (MAX_UPLOAD + 1), 'docx'),
                           (docx('<!DOCTYPE x [<!ENTITY x "bad">]><x>&x;</x>'), 'docx')]:
            with self.subTest(kind=kind, size=len(data)), self.assertRaises(ValueError):
                extract_resume(data, kind)

    def test_upload_endpoint_validation_and_origin(self):
        with TestClient(app) as client:
            good = client.post('/api/resume-text?kind=docx', content=docx())
            self.assertEqual(good.status_code, 200)
            self.assertIn('Python', good.json()['text'])
            self.assertEqual(client.post('/api/resume-text?kind=doc', content=b'bad').status_code, 415)
            self.assertEqual(client.post('/api/resume-text?kind=pdf', content=b'bad').status_code, 422)
            self.assertEqual(client.post('/api/resume-text?kind=pdf', content=b'x' * (MAX_UPLOAD+1)).status_code, 413)
            self.assertEqual(client.post('/api/resume-text?kind=docx', content=docx(),
                                        headers={'Origin': 'https://evil.example'}).status_code, 403)
