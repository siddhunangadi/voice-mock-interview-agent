from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree

from pypdf import PdfReader

MAX_UPLOAD = 5 * 1024 * 1024


def extract_resume(data: bytes, kind: str) -> str:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('Choose a non-empty file under 5 MB.')
    try:
        if kind == 'pdf' and data.startswith(b'%PDF-'):
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('Remove the PDF password before uploading.')
            if len(reader.pages) > 20:
                raise ValueError('Upload a resume with no more than 20 pages.')
            paragraphs = []
            for page in reader.pages:
                stream = page.get_contents()
                if stream and len(stream.get_data()) > 5 * 1024 * 1024:
                    raise ValueError('This PDF is too complex. Export a simpler PDF or paste the text.')
                paragraphs.append(page.extract_text() or '')
        elif kind == 'docx' and data.startswith(b'PK'):
            with ZipFile(BytesIO(data)) as archive:
                names = [n for n in archive.namelist() if n == 'word/document.xml' or
                         (n.startswith(('word/header', 'word/footer')) and n.endswith('.xml'))]
                if 'word/document.xml' not in names or sum(archive.getinfo(n).file_size for n in names) > MAX_UPLOAD:
                    raise ValueError('Invalid or oversized Word document. Export it again or paste the text.')
                paragraphs = []
                for name in names:
                    xml = archive.read(name)
                    # Reject declarations before parsing, including UTF-16 encoded XML.
                    if b'<!DOCTYPE' in xml.replace(b'\x00', b'').upper() or b'<!ENTITY' in xml.replace(b'\x00', b'').upper():
                        raise ValueError('Unsupported document content. Export a new DOCX or paste the text.')
                    root = ElementTree.fromstring(xml)
                    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                    paragraphs.extend(''.join(node.text or '' for node in p.iter(ns + 't'))
                                      for p in root.iter(ns + 'p'))
        else:
            raise ValueError('Upload a valid PDF or DOCX file. Older .doc files are not supported.')
        text = '\n'.join(paragraphs).replace('\x00', '').strip()
    except ValueError:
        raise
    except Exception:
        raise ValueError('Could not read this file. Export it again as PDF or DOCX, or paste the text.') from None
    if len(text) < 30:
        raise ValueError('Not enough readable text. For scanned resumes, use a searchable PDF or paste the text.')
    if len(text) > 20000:
        raise ValueError('Resume text exceeds 20,000 characters. Upload a shorter resume or paste the relevant sections.')
    return text
