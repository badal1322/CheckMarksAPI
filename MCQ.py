import re
import pandas as pd
import pdfplumber
import logging

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class JEEExamParser:
    """A class to parse JEE exam response PDFs and convert them to CSV format."""

    def __init__(self, pdf_path: str, output_csv: str):
        """Initialize with path to PDF file and output CSV path."""
        self.pdf_path = pdf_path
        self.output_csv = output_csv
        self.exam_data = []

    def extract_text_from_pdf(self) -> str:
        """Extract all text from the PDF."""
        full_text = ""
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
                    logger.info(f"Processed page {page_num}/{len(pdf.pages)}")

            if not full_text:
                logger.error("Extracted text is empty")
            else:
                logger.info(f"Successfully extracted {len(full_text)} characters from PDF")

            return full_text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""

    def find_all_questions(self, text: str):
        """Find all questions in the text, focusing only on MCQs."""
        all_questions = []

        # Find all instances of "Question Type : MCQ"
        question_sections = re.split(r"Question Type\s*:\s*MCQ", text)[1:]  # Skip the first element which is before any question

        for i, section in enumerate(question_sections):
            logger.debug(f"Processing MCQ section {i+1}")

            # Extract question ID
            id_match = re.search(r"Question ID\s*:\s*(\d+)", section)
            if not id_match:
                logger.warning(f"Could not find Question ID in section {i+1}")
                continue

            question_id = id_match.group(1)
            logger.debug(f"Found MCQ question with ID: {question_id}")

            # Extract this question's data
            q_data = self.extract_mcq_data(section, question_id)
            if q_data:
                all_questions.append(q_data)

        logger.info(f"Found {len(all_questions)} MCQ questions in total")
        return all_questions

    def extract_mcq_data(self, section: str, question_id: str):
        """Extract data for an MCQ question from its section."""
        try:
            data = {"type": "mcq", "question_id": question_id}

            # Extract option IDs with more robust pattern
            option_pattern = r"Option (\d) ID\s*:\s*(\d+)"
            option_matches = re.finditer(option_pattern, section)

            # Store option number to ID mapping
            option_id_map = {}

            for match in option_matches:
                option_num = match.group(1)
                option_id = match.group(2)
                data[f"option_{option_num}_id"] = option_id
                option_id_map[option_num] = option_id

            # Fill in missing options with empty strings
            for i in range(1, 5):
                if f"option_{i}_id" not in data:
                    data[f"option_{i}_id"] = ""

            # Extract status
            status_match = re.search(r"Status\s*:\s*(.*?)(?=Chosen|\n|$)", section, re.DOTALL)
            data["status"] = status_match.group(1).strip() if status_match else "Not Answered"

            # Extract chosen option number
            chosen_match = re.search(r"Chosen Option\s*:\s*(\S*)", section)
            chosen_option_num = chosen_match.group(1).strip() if chosen_match else ""
            data["chosen_option"] = chosen_option_num

            # Set chosen option ID based on chosen option number
            if chosen_option_num and chosen_option_num in option_id_map:
                data["chosen_option_id"] = option_id_map[chosen_option_num]
            else:
                data["chosen_option_id"] = ""

            # No "Given Answer" field for MCQ
            data["given_answer"] = ""

            return data
        except Exception as e:
            logger.error(f"Error extracting MCQ data for question {question_id}: {e}")
            return None

    def parse_exam_pdf(self):
        """Parse the entire PDF and extract all question data."""
        logger.info(f"Parsing PDF: {self.pdf_path}")

        full_text = self.extract_text_from_pdf()
        if not full_text:
            logger.error("No text extracted from PDF")
            return []

        self.exam_data = self.find_all_questions(full_text)

        # Sort by question_id
        self.exam_data.sort(key=lambda x: int(x.get("question_id", "0")))

        return self.exam_data

    def export_to_csv(self):
        """Export parsed data to CSV."""
        if not self.exam_data and not self.parse_exam_pdf():
            logger.error("No data to export")
            return False
        try:
            df = pd.DataFrame(self.exam_data)
            # Expected column format
            columns = ["type", "question_id", "option_1_id", "option_2_id",
                       "option_3_id", "option_4_id", "status", "chosen_option",
                       "chosen_option_id", "given_answer"]
            # Add missing columns
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            # Reorder columns
            df = df[columns]
            # Export to CSV
            df.to_csv(self.output_csv, index=False)
            logger.info(f"Successfully exported data to {self.output_csv} with {len(df)} rows")
            return True
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False

if __name__ == "__main__":
    # Set file paths here
    pdf_path = "/Users/priyanshubadal/Downloads/AADITYA PASSI_250227_090945.pdf"  # Change this
    csv_path = "/Users/priyanshubadal/Desktop/CheckMarksAPI/MCQ.csv" # Change this

    parser = JEEExamParser(pdf_path, csv_path)
    parser.parse_exam_pdf()
    parser.export_to_csv()
    logger.info("Process completed")