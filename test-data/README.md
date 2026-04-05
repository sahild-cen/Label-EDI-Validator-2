# Test Data Files

This directory contains sample files for testing the Label & EDI Validation Tool.

## Files

### Label Files

- **sample_label.zpl** - A sample ZPL (Zebra Programming Language) shipping label
  - Contains tracking number, sender/recipient addresses, and barcode
  - Can be used to test ZPL validation

### EDI Files

- **sample_edi_x12.txt** - A sample X12 850 Purchase Order EDI file
  - Standard ANSI X12 format with segment delimiter (~)
  - Contains ISA, GS, ST, BEG, PO1, and other standard segments

- **sample_edi_edifact.txt** - A sample EDIFACT ORDERS message
  - UN/EDIFACT format with segment delimiter (')
  - Contains UNB, UNH, BGM, LIN, and other standard segments

## How to Use

### Testing Label Validation

1. Go to the Validation Dashboard
2. Select a carrier (upload carrier specs first if needed)
3. Upload `sample_label.zpl`
4. Check "This is a ZPL file"
5. Click "Validate Label"

### Testing EDI Validation

1. Go to the Validation Dashboard
2. Select a carrier (upload carrier specs first if needed)
3. Upload either `sample_edi_x12.txt` or `sample_edi_edifact.txt`
4. Click "Validate EDI"

## Creating Your Own Test Files

### ZPL Labels

ZPL files are text files containing Zebra printer commands. Basic structure:

```
^XA                    (Start of label)
^FO50,50              (Field origin - position)
^A0N,50,50            (Font selection)
^FDYour Text^FS       (Field data)
^BY3                  (Barcode parameters)
^BCN,100,Y,N,N        (Code 128 barcode)
^FDBarcode Data^FS    (Barcode data)
^XZ                   (End of label)
```

### X12 EDI Files

X12 files use:
- Segment delimiter: `~`
- Element delimiter: `*`
- Sub-element delimiter: `>`

Basic structure:
```
ISA*...*~
GS*...*~
ST*850*0001~
[Transaction content]
SE*...*~
GE*...*~
IEA*...*~
```

### EDIFACT EDI Files

EDIFACT files use:
- Segment delimiter: `'`
- Element delimiter: `+`
- Sub-element delimiter: `:`

Basic structure:
```
UNB+...+'
UNH+...+'
[Message content]
UNT+...+'
UNZ+...+'
```

## Expected Validation Results

### Sample Label (ZPL)

**Expected to PASS** if carrier rules require:
- Tracking number field
- Sender address
- Recipient address
- Barcode

### Sample EDI (X12)

**Expected to PASS** if carrier rules require:
- ISA, GS, ST header segments
- Transaction set (850)
- SE, GE, IEA trailer segments

### Sample EDI (EDIFACT)

**Expected to PASS** if carrier rules require:
- UNB, UNH header segments
- Message type (ORDERS)
- UNT, UNZ trailer segments

## Modifying Test Files

You can modify these files to test different validation scenarios:

1. **Remove required segments** - Test missing segment detection
2. **Change segment order** - Test segment order validation
3. **Remove barcodes** - Test barcode requirement validation
4. **Modify field formats** - Test format validation

## Note on Carrier Specifications

These sample files are generic examples. For production use:
1. Upload real carrier specification PDFs
2. The system will generate appropriate rule templates
3. Validation will be based on actual carrier requirements
