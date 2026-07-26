# Split Bible Files

These large PDF files have been split into smaller parts to accommodate GitHub's file size limits.

## Files

### Peshitta - Ancient Syriac Bible.pdf (56.65 MB)
- `Peshitta - Ancient Syriac Bible.pdf.part1of2` (30.00 MB)
- `Peshitta - Ancient Syriac Bible.pdf.part2of2` (26.65 MB)

### The Ante Nicene Fathers.pdf (52.27 MB)
- `The Ante Nicene fathers.pdf.part1of2` (30.00 MB)
- `The Ante Nicene fathers.pdf.part2of2` (22.27 MB)

## How to Reassemble

### Option 1: Use the Python Script (Recommended)

1. Download all parts for the file you want
2. Run the reassembly script:
   ```bash
   python reassemble_bibles.py
   ```
   Or for a specific file:
   ```bash
   python reassemble_bibles.py "Peshitta - Ancient Syriac Bible.pdf"
   ```

### Option 2: Manual Reassembly

**Windows (Command Prompt):**
```cmd
copy /b "Peshitta - Ancient Syriac Bible.pdf.part1of2" + "Peshitta - Ancient Syriac Bible.pdf.part2of2" "Peshitta - Ancient Syriac Bible.pdf"
```

**Linux/Mac:**
```bash
cat "Peshitta - Ancient Syriac Bible.pdf.part1of2" "Peshitta - Ancient Syriac Bible.pdf.part2of2" > "Peshitta - Ancient Syriac Bible.pdf"
```

### Option 3: Use Archive Tools

Most archive managers (7-Zip, WinRAR) can join split files:
1. Select all parts
2. Right-click → "Combine files" or "Extract here"

## Verification

After reassembly, verify the file integrity:
- **Peshitta**: Should be 56.65 MB (59,416,832 bytes)
- **Ante-Nicene Fathers**: Should be 52.27 MB (54,810,265 bytes)

## About These Texts

**Peshitta - Ancient Syriac Bible**
- Date: 2nd-5th centuries CE
- Language: Syriac
- Significance: Standard Syriac translation of the Bible, used by Syriac churches

**The Ante-Nicene Fathers**
- Date: 100-325 CE
- Contents: 38 volumes of writings from early Church Fathers
- Significance: Primary source for early Christian theology

## Full Collection

See the complete collection at:
https://github.com/kaibuzz0/chain-breaker/tree/main/bibles

## License

These texts are in the public domain or used under fair use for preservation purposes.
