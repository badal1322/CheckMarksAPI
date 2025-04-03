from io import BytesIO
import os
import json
import asyncio
import tempfile
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
import uvicorn
from models import extract_mcq_from_pdf, extract_sa_from_pdf

app = FastAPI(
    title="PDF Question Extractor API",
    description="API for extracting MCQ and Short Answer questions from PDF files"
)


async def save_temp_file(file: UploadFile) -> str:
    """Save uploaded file asynchronously and return file path"""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        contents = await file.read()
        await asyncio.to_thread(temp_file.write, contents)
        temp_file.close()
        return temp_file.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")


async def process_file_in_memory(file: UploadFile) -> BytesIO:
    """Process uploaded file in memory without saving to disk"""
    contents = await file.read()
    return BytesIO(contents)


@app.post("/extract/mcq", response_class=JSONResponse)
async def extract_mcq(file: UploadFile = File(...), date: str = Form(...)):
    try:
        print(f"Received date in MCQ endpoint: {date}")  # Debug log
        
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        # Validate date format (DD_MM_YY)
        if not date or not date.replace('_', '').isdigit() or len(date.split('_')) != 3:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected DD_MM_YY (e.g., 04_04_24)")
            
        answer_key_filename = f"{date}.json"
        print(f"Looking for answer key: {answer_key_filename}")  # Debug log

        # Construct the path to the answer key file
        answer_key_folder = "AnswerKey"
        answer_key_path = os.path.join(answer_key_folder, answer_key_filename)
        print(f"Full answer key path: {answer_key_path}")  # Debug log

        if not os.path.exists(answer_key_path):
            raise HTTPException(status_code=404, detail=f"Answer key file not found: {answer_key_path}")

        # Process file in memory
        pdf_bytes = await process_file_in_memory(file)

        # Extract MCQ data using BytesIO
        mcq_data = await asyncio.to_thread(extract_mcq_from_pdf, pdf_bytes)
        print(f"Extracted MCQ data shape: {mcq_data.shape}")  # Debug log

        # Load and validate answer key
        try:
            with open(answer_key_path, "r") as f:
                answer_key = json.load(f)
                print(f"Loaded answer key with {len(answer_key)} entries")  # Debug log
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Invalid answer key JSON: {str(e)}")

        # Check answer key structure
        if not all("id" in item and "correct_option" in item for item in answer_key):
            raise HTTPException(status_code=500, detail="Invalid answer key structure")

        # Create answer key dictionary with proper keys
        answer_key_dict = {item["id"]: item["correct_option"] for item in answer_key}

        correct_count = incorrect_count = skipped_count = total_score = 0

        # Process MCQ answers
        for _, row in mcq_data.iterrows():
            question_id = str(row.get("question_id"))  # Convert to string for comparison
            chosen_option_id = str(row.get("chosen_option_id")) if row.get("chosen_option_id") else ""

            if question_id not in answer_key_dict:
                print(f"Question ID {question_id} not found in answer key")  # Debug log
                continue

            if not chosen_option_id:
                skipped_count += 1
            elif chosen_option_id == str(answer_key_dict[question_id]):
                correct_count += 1
                total_score += 4
            else:
                incorrect_count += 1
                total_score -= 1

        return {
            "mcq_data": mcq_data.to_dict(orient="records"),
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
        print(f"Error processing MCQ: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@app.post("/extract/sa", response_class=JSONResponse)
async def extract_sa(file: UploadFile = File(...), date: str = Form(...)):
    try:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        # Validate date format
        if not date or not date.replace('_', '').isdigit() or len(date.split('_')) != 3:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected DD_MM_YY")

        # Process file in memory
        pdf_bytes = await process_file_in_memory(file)
        
        # Load answer key
        answer_key_path = os.path.join("AnswerKey", f"{date}.json")
        if not os.path.exists(answer_key_path):
            raise HTTPException(status_code=404, detail=f"Answer key not found for date: {date}")

        with open(answer_key_path, 'r') as f:
            answer_key = json.load(f)

        # Extract SA data using BytesIO
        sa_data = await asyncio.to_thread(extract_sa_from_pdf, pdf_bytes)

        # Process SA answers
        answer_key_dict = {item["id"]: item["correct_option"] for item in answer_key}
        results = []
        total_score = correct_count = incorrect_count = skipped_count = 0

        for _, row in sa_data.iterrows():
            question_id = str(row.get("question_id"))
            given_answer = str(row.get("answer", "")).strip()

            if question_id not in answer_key_dict:
                continue

            correct_answer = str(answer_key_dict[question_id])

            if not given_answer or given_answer.upper() == "NULL":
                skipped_count += 1
                status = "Not Answered"
                points = 0
            elif given_answer == correct_answer:
                correct_count += 1
                total_score += 4
                status = "Correct"
                points = 4
            else:
                incorrect_count += 1
                total_score -= 1
                status = "Incorrect"
                points = -1

            results.append({
                "question_id": question_id,
                "given_answer": given_answer,
                "correct_answer": correct_answer,
                "status": status,
                "points": points
            })

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
        print(f"Error processing SA: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.get("/")
async def root():
    return {"message": "Welcome to the PDF Question Extractor API. Use /extract/mcq or /extract/sa endpoints."}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
