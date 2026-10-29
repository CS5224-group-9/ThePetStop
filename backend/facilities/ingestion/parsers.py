import hashlib
import re
from io import BytesIO

import pdfplumber

from facilities.animals import ANIMAL_COLUMNS

PARSER_VERSION = "2"
VET = "vet"
PET_SHOP = "pet_shop"
SOURCES = {VET, PET_SHOP}
POSTAL_CODE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
VET_SERIAL = re.compile(r"^\s*(\d{1,3})\s*$")
PET_SHOP_LICENCE = re.compile(r"^[A-Z0-9]{6,16}$")
PLACEHOLDERS = {"", "NIL", "NA", "N/A", "NONE"}


class RegistryParseError(ValueError):
    """The source PDF could not be converted into a complete registry snapshot."""


def _clean(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\n", " ").split())


def _parts(*values):
    return [
        _clean(value) for value in values if _clean(value).upper() not in PLACEHOLDERS
    ]


def _address(*values):
    parts = _parts(*values)
    if not parts:
        return ""
    return ", ".join(parts)


def _source_key(source, name, address, postal_code, licence_no=""):
    if licence_no:
        return licence_no
    identity = "|".join(
        _clean(value).casefold() for value in (source, name, postal_code, address)
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _vet_records(pdf):
    records = []
    for page in pdf.pages:
        text_postcodes = {}
        for line in (page.extract_text() or "").splitlines():
            match = re.match(r"^\s*(\d{1,3})\s+(.+)$", line)
            if match:
                postal = POSTAL_CODE.search(match.group(2))
                if postal:
                    text_postcodes[match.group(1)] = postal.group(1)

        for table in page.extract_tables():
            for row in table:
                if not row or not VET_SERIAL.fullmatch(_clean(row[0])):
                    continue
                serial = _clean(row[0])
                cells = [_clean(cell) for cell in row]
                if len(cells) < 5:
                    raise RegistryParseError(f"Veterinary row {serial} is incomplete")

                postal = next(
                    (
                        match.group(1)
                        for cell in cells
                        if (match := POSTAL_CODE.search(cell))
                    ),
                    text_postcodes.get(serial, ""),
                )
                name = cells[1]
                block = cells[2]
                street = cells[3]
                building = cells[4]
                floor = cells[5] if len(cells) > 5 else ""
                unit = cells[6] if len(cells) > 6 else ""
                unit_text = ""
                if floor and floor.upper() not in PLACEHOLDERS:
                    unit_text = f"#{floor}"
                    if unit and unit.upper() not in PLACEHOLDERS:
                        unit_text += f"-{unit}"
                address = _address(
                    f"{block} {street}".strip(),
                    building,
                    unit_text,
                    f"Singapore {postal}",
                )
                if not name or not postal or not address:
                    raise RegistryParseError(
                        f"Veterinary row {serial} lacks a name, address, or postal code"
                    )

                records.append(
                    {
                        "source_id": VET,
                        "source_key": _source_key(VET, name, address, postal),
                        "facility_type": "vet",
                        "name": name,
                        "licence_no": None,
                        "address": address,
                        "postal_code": postal,
                    }
                )

    serials = [int(record_serial) for record_serial in _vet_serials(pdf)]
    if not records or serials != list(range(1, len(serials) + 1)):
        raise RegistryParseError(
            "Veterinary registry is empty or its serial sequence has gaps"
        )
    return records


def _vet_serials(pdf):
    serials = set()
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                if row and VET_SERIAL.fullmatch(_clean(row[0])):
                    serials.add(_clean(row[0]))
    return sorted(serials, key=int)


def _pet_shop_records(pdf):
    records = []
    for page in pdf.pages:
        revoked = page.search(r"(?i)List\s+of\s+Revoked\s+Pet\s+Shop\s+Licences")
        revoked_top = min((heading["top"] for heading in revoked), default=None)
        for found_table in page.find_tables():
            if revoked_top is not None and found_table.bbox[1] >= revoked_top:
                continue
            table = found_table.extract()
            animal_columns = None
            for row in table:
                if row and [_clean(cell) for cell in row[8:]] == list(ANIMAL_COLUMNS):
                    animal_columns = list(ANIMAL_COLUMNS.values())
                    continue
                if not row or not PET_SHOP_LICENCE.fullmatch(_clean(row[0])):
                    continue
                cells = [_clean(cell) for cell in row]
                if len(cells) != 14 or animal_columns is None:
                    raise RegistryParseError(
                        f"Pet shop {cells[0]} has an incomplete row"
                    )
                markers = cells[8:]
                if (
                    any(marker not in {"", "*"} for marker in markers)
                    or "*" not in markers
                ):
                    raise RegistryParseError(
                        f"Pet shop {cells[0]} has invalid animal approvals"
                    )
                approved_animals = [
                    animal
                    for animal, marker in zip(animal_columns, markers, strict=True)
                    if marker == "*"
                ]
                licence_no, name = cells[0], cells[1]
                postal = POSTAL_CODE.search(cells[7])
                address = _address(
                    f"{cells[2]} {cells[3]}".strip(),
                    cells[6],
                    f"{cells[4]}{cells[5]}".strip(),
                    f"Singapore {postal.group(1)}" if postal else "",
                )
                if not name or not postal or not address:
                    raise RegistryParseError(
                        f"Pet shop {licence_no} lacks a name, address, or postal code"
                    )
                records.append(
                    {
                        "source_id": PET_SHOP,
                        "source_key": licence_no,
                        "facility_type": "pet_shop",
                        "name": name,
                        "licence_no": licence_no,
                        "address": address,
                        "postal_code": postal.group(1),
                        "approved_animals": approved_animals,
                    }
                )

    if not records or len({record["source_key"] for record in records}) != len(records):
        raise RegistryParseError(
            "Pet-shop registry is empty or contains duplicate licences"
        )
    return records


def parse_registry_pdf(content, source):
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise RegistryParseError("Registry download is not a PDF")
    if source not in SOURCES:
        raise RegistryParseError(f"Unsupported AVS source: {source}")
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            records = _vet_records(pdf) if source == VET else _pet_shop_records(pdf)
    except RegistryParseError:
        raise
    except Exception as error:
        raise RegistryParseError("AVS PDF could not be parsed") from error

    keys = [record["source_key"] for record in records]
    if len(set(keys)) != len(keys):
        raise RegistryParseError("AVS PDF contains duplicate facility identities")
    return records
