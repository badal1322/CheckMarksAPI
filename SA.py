from fastapi import APIRouter, HTTPException, UploadFile, File
import json
import tempfile
from models import extract_sa_from_pdf

sa_router = APIRouter()

# Load answer key
with open("answer_key.json", "r") as file:
    answer_key = json.load(file)

# Convert answer key to a dictionary for faster lookup
answer_dict = {q["question_id"]: q["correct_option_id"] for q in answer_key}

def match_answer(user_answer, correct_answer):
    """
    Matches answers, considering case insensitivity and numeric conversion.
    """
    if correct_answer in ["DROP", ""]:  # Ignore invalid answers
        return False

    try:
        return float(user_answer) == float(correct_answer)
    except ValueError:
        return user_answer.strip().lower() == correct_answer.strip().lower()

@sa_router.post("/extract/sa")
async def evaluate_sa(file: UploadFile = File(...)):
    """
    Extract Short Answer Questions from a PDF file and calculate scores.
    Marking scheme:
    - Correct answer: +4 marks
    - Incorrect answer: -1 mark
    - Unattempted: 0 marks
    """
    # Validate file is a PDF
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Save uploaded file temporarily
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    try:
        contents = await file.read()
        temp_file.write(contents)
        temp_file.close()

        # Process the PDF
        sa_data = extract_sa_from_pdf(temp_file.name)

        total_score = 0
        correct_count = 0
        incorrect_count = 0
        skipped_count = 0
        results = []

        # Process each question
        for _, row in sa_data.iterrows():
            q_id = str(row.get("question_id"))
            given_answer = str(row.get("answer")).strip()

            # Skip questions not in answer key
            if q_id not in answer_dict:
                continue

            correct_answer = str(answer_dict.get(q_id)).strip()

            # Create detailed result for this question
            result = {
                "type": "sa",
                "question_id": q_id,
                "given_answer": given_answer,
                "correct_answer": correct_answer,
                "status": "",
                "points": 0
            }

            # Check answer status
            if given_answer.upper() == "NULL" or not given_answer:
                skipped_count += 1
                result["status"] = "Not Answered"
            elif given_answer == correct_answer:
                correct_count += 1
                total_score += 4
                result["status"] = "Correct"
                result["points"] = 4
            else:
                incorrect_count += 1
                total_score -= 1
                result["status"] = "Incorrect"
                result["points"] = -1

            results.append(result)

        # Return formatted response matching MCQ format
        return {
            "sa_data": results,
            "filename": file.filename,
            "score_summary": {
                "correct_questions": correct_count,
                "incorrect_questions": incorrect_count,
                "skipped_questions": skipped_count,
                "total_questions": correct_count + incorrect_count + skipped_count,
                "total_score": total_score,
                "scoring_system": "+4 for correct, -1 for incorrect, 0 for skipped"
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if temp_file.name and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
