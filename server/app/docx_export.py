"""Create a small, dependency-free Word document from user-approved composer text."""
from __future__ import annotations

from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
from io import BytesIO


def _paragraph(line: str) -> str:
    bullet = line.lstrip().startswith(('- ', '* ', '• '))
    text = line.lstrip()[2:] if bullet else line
    prefix = '<w:r><w:t>• </w:t></w:r>' if bullet else ''
    return f'<w:p>{prefix}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def make_docx(text: str) -> bytes:
    body = ''.join(_paragraph(line) if line else '<w:p/>' for line in text.splitlines()) or '<w:p/>'
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body>{body}<w:sectPr/></w:body></w:document>')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '</Types>')
    relationships = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                     '</Relationships>')
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as package:
        package.writestr('[Content_Types].xml', content_types)
        package.writestr('_rels/.rels', relationships)
        package.writestr('word/document.xml', document)
    return buffer.getvalue()
