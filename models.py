from io import BytesIO
import pandas as pd
import pdfplumber
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class JEEExamParser:
    """A class to parse JEE exam response PDFs."""

    def __init__(self, pdf_bytes: BytesIO):
        """Initialize with PDF bytes."""
        # Convert to BytesIO if needed
        if isinstance(pdf_bytes, str):
            pdf_bytes = BytesIO(pdf_bytes.encode())
        elif isinstance(pdf_bytes, bytes):
            pdf_bytes = BytesIO(pdf_bytes)
            
        self.pdf_bytes = pdf_bytes
        self.exam_data = []

    def extract_text_from_pdf(self) -> str:
        """Extract all text from the PDF."""
        full_text = ""
        try:
            with pdfplumber.open(self.pdf_bytes) as pdf:
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
        question_sections = re.split(r"Question Type\s*:\s*MCQ", text)[1:]

        for i, section in enumerate(question_sections):
            id_match = re.search(r"Question ID\s*:\s*(\d+)", section)
            if not id_match:
                logger.warning(f"Could not find Question ID in section {i+1}")
                continue

            question_id = id_match.group(1)
            q_data = self.extract_mcq_data(section, question_id)
            if q_data:
                all_questions.append(q_data)

        logger.info(f"Found {len(all_questions)} MCQ questions in total")
        return all_questions

    def extract_mcq_data(self, section: str, question_id: str):
        """Extract data for an MCQ question from its section."""
        try:
            data = {"type": "mcq", "question_id": question_id}
            option_pattern = r"Option (\d) ID\s*:\s*(\d+)"
            option_matches = re.finditer(option_pattern, section)
            option_id_map = {}

            for match in option_matches:
                option_num = match.group(1)
                option_id = match.group(2)
                data[f"option_{option_num}_id"] = option_id
                option_id_map[option_num] = option_id

            for i in range(1, 5):
                if f"option_{i}_id" not in data:
                    data[f"option_{i}_id"] = ""

            status_match = re.search(r"Status\s*:\s*(.*?)(?=Chosen|\n|$)", section, re.DOTALL)
            data["status"] = status_match.group(1).strip() if status_match else "Not Answered"

            chosen_match = re.search(r"Chosen Option\s*:\s*(\S*)", section)
            chosen_option_num = chosen_match.group(1).strip() if chosen_match else ""
            data["chosen_option"] = chosen_option_num

            if chosen_option_num and chosen_option_num in option_id_map:
                data["chosen_option_id"] = option_id_map[chosen_option_num]
            else:
                data["chosen_option_id"] = ""

            data["given_answer"] = ""
            return data
        except Exception as e:
            logger.error(f"Error extracting MCQ data for question {question_id}: {e}")
            return None

    def parse_exam_pdf(self):
        """Parse the entire PDF and extract all question data."""
        full_text = self.extract_text_from_pdf()
        if not full_text:
            logger.error("No text extracted from PDF")
            return []

        self.exam_data = self.find_all_questions(full_text)
        self.exam_data.sort(key=lambda x: int(x.get("question_id", "0")))
        return self.exam_data

def extract_text_from_pdf_bytes(pdf_bytes: BytesIO) -> list:
    """Extract text from PDF bytes and return as a list of lines."""
    try:
        # Convert to BytesIO if string is received
        if isinstance(pdf_bytes, str):
            pdf_bytes = BytesIO(pdf_bytes.encode())
        elif isinstance(pdf_bytes, bytes):
            pdf_bytes = BytesIO(pdf_bytes)
            
        # Reset buffer position
        pdf_bytes.seek(0)
        extracted_text = ""
        
        with pdfplumber.open(pdf_bytes) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
                logger.info(f"Processed page {page_num}/{len(pdf.pages)}")
                
        if not extracted_text:
            logger.error("No text extracted from PDF")
            return []
            
        return extracted_text.split("\n")
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return []

def extract_mcq_from_pdf(pdf_bytes: BytesIO):
    """Extract Multiple Choice Questions from a PDF file."""
    logger.info("Processing PDF for MCQs from memory")
    
    # Convert to BytesIO if needed
    if isinstance(pdf_bytes, str):
        pdf_bytes = BytesIO(pdf_bytes.encode())
    elif isinstance(pdf_bytes, bytes):
        pdf_bytes = BytesIO(pdf_bytes)
        
    parser = JEEExamParser(pdf_bytes)
    exam_data = parser.parse_exam_pdf()
    
    if not exam_data:
        columns = ["type", "question_id", "option_1_id", "option_2_id",
                  "option_3_id", "option_4_id", "status", "chosen_option",
                  "chosen_option_id", "given_answer"]
        return pd.DataFrame(columns=columns)
    
    return pd.DataFrame(exam_data)

def extract_sa_from_pdf(pdf_bytes: BytesIO):
    """Extract Short Answer Questions from a PDF file."""
    logger.info("Processing PDF for Short Answers from memory")
    
    # Convert to BytesIO if needed
    if isinstance(pdf_bytes, str):
        pdf_bytes = BytesIO(pdf_bytes.encode())
    elif isinstance(pdf_bytes, bytes):
        pdf_bytes = BytesIO(pdf_bytes)
        
    text_lines = extract_text_from_pdf_bytes(pdf_bytes)
    
    given_values = []
    question_id = None

    for i, line in enumerate(text_lines):
        match = re.search(r"Given(\d+)?", line)
        if match:
            value = match.group(1) if match.group(1) else "NULL"
            for j in range(i + 1, len(text_lines)):
                qid_match = re.search(r"Question ID :(\d+)", text_lines[j])
                if qid_match:
                    question_id = qid_match.group(1)
                    break
            given_values.append((question_id, value))
    
    df = pd.DataFrame(given_values, columns=["question_id", "answer"])
    if "question" not in df.columns:
        df["question"] = ""
    
    return df