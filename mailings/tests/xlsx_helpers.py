from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook


def write_workbook(path: Path, rows, *, write_only: bool = False) -> Path:
    workbook = Workbook(write_only=write_only)
    worksheet = workbook.create_sheet() if write_only else workbook.active
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def corrupt_worksheet_xml(source: Path, target: Path) -> Path:
    worksheet_path = "xl/worksheets/sheet1.xml"

    with ZipFile(source) as source_archive:
        with ZipFile(target, "w", ZIP_DEFLATED) as target_archive:
            for entry in source_archive.infolist():
                content = source_archive.read(entry.filename)
                if entry.filename == worksheet_path:
                    content = content[:-20]
                target_archive.writestr(entry, content)

    return target
