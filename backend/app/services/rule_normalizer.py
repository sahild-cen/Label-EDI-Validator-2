FIELD_MAPPING = {
    # Country
    "country code": "country_code",
    "destination country code": "country_code",
    "origin country code": "country_code",

    # Postal
    "postcode": "postal_code",
    "postal code": "postal_code",
    "zip code": "postal_code",
    "zip": "postal_code",
    "post code": "postal_code",

    # Routing
    "routing barcode": "routing_barcode",
    "routing code": "routing_barcode",
    "routing information bar code": "routing_barcode",
    "sort code": "routing_barcode",

    # License plate
    "license plate": "license_plate",
    "licence plate": "license_plate",
    "licence plate identifier": "license_plate",
    "sscc": "license_plate",

    # Tracking
    "tracking number": "tracking_number",
    "tracking_number": "tracking_number",
    "consignment number": "tracking_number",

    # Shipment
    "shipment number": "shipment_number",
    "shipment_number": "shipment_number",
    "airwaybill": "shipment_number",
    "awb": "shipment_number",
    "waybill": "shipment_number",
    "air waybill": "shipment_number",
    "consignment id": "shipment_number",

    # Label
    "label width": "label_width",
    "label height": "label_height",
    "label length": "label_height",
    "label orientation": "label_orientation",
    "label size": "label_dimensions",
    "label dimensions": "label_dimensions",

    # Sender / receiver
    "sender name": "sender_name",
    "shipper name": "sender_name",
    "sender address": "sender_address",
    "shipper address": "sender_address",
    "receiver name": "receiver_name",
    "recipient name": "receiver_name",
    "consignee name": "receiver_name",
    "receiver address": "receiver_address",
    "recipient address": "receiver_address",
    "destination address": "receiver_address",

    # Weight
    "weight": "weight",
    "gross weight": "weight",
    "actual weight": "weight",
    "package weight": "weight",

    # Service
    "service type": "service_type",
    "service code": "service_type",
    "product code": "service_type",

    # Barcode
    "barcode": "barcode",
    "linear barcode": "barcode",
    "awb barcode": "barcode",

    # Reference
    "reference number": "reference_number",
    "reference": "reference_number",
    "customer reference": "reference_number",

    # Piece count
    "piece count": "piece_count",
    "number of pieces": "piece_count",
    "total pieces": "piece_count",
}


def normalize_rules(rules):
    normalized = []

    for rule in rules:
        field_name = rule.get("field_name", "").lower().strip()

        standardized_field = FIELD_MAPPING.get(
            field_name,
            field_name.replace(" ", "_").replace("-", "_")
        )

        # Clean up double underscores
        standardized_field = standardized_field.replace("__", "_").strip("_")

        normalized.append({
            "field": standardized_field,
            "required": rule.get("required", False),
            "regex": rule.get("regex", ""),
            "description": rule.get("description", "")
        })

    return normalized