import re
import csv
import pdfplumber

# Define the PDF file path
pdf_path = "/content/sample.pdf"
output_csv_path = "/content/sample.csv"

# Function to extract text from PDF
def extract_text_from_pdf(pdf_path):
    extracted_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                extracted_text += page_text + "\n"
    return extracted_text.split("\n")  # Return as a list of lines

# Extract text lines from PDF
text_lines = extract_text_from_pdf(pdf_path)

# Extract numerical values after "Given" along with Question ID
given_values = []
question_id = None

for i, line in enumerate(text_lines):
    match = re.search(r"Given(\d+)?", line)
    if match:
        value = match.group(1) if match.group(1) else "NULL"
        # Find the next question ID
        for j in range(i + 1, len(text_lines)):
            qid_match = re.search(r"Question ID :(\d+)", text_lines[j])
            if qid_match:
                question_id = qid_match.group(1)
                break
        given_values.append((question_id, value))

# Write extracted values to a CSV file
with open(output_csv_path, "w", newline="", encoding="utf-8") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(["Question ID", "Extracted Number"])  # Header row
    for qid, value in given_values:
        writer.writerow([qid, value])

print(f"CSV file saved at: {output_csv_path}")