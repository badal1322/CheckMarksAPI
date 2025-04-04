from io import BytesIO
import os
import json
import asyncio
import tempfile
import requests
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
import uvicorn
from models import extract_mcq_from_pdf, extract_sa_from_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ANSWER_KEY_DRIVE_MAP = {
    "04_04_24": "1-Etixccitmyanw18TkFToNu602MxsWBa"
}

app = FastAPI(
    title="PDF Question Extractor API",
    description="API for extracting MCQ and Short Answer questions from PDF files"
)


def get_answer_key_from_drive(file_id: str) -> dict:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


async def process_file_in_memory(file: UploadFile) -> BytesIO:
    """Process uploaded file in memory without saving to disk"""
    contents = await file.read()
    return BytesIO(contents)


@app.post("/extract/mcq", response_class=JSONResponse)
async def extract_mcq(file: UploadFile = File(...), date: str = Form(...)):
    try:
        print(f"Received date in MCQ endpoint: {date}")  # Debug log
        print(f"Received file: {file.filename}")
        print(f"Current directory: {os.getcwd()}")

        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        # Validate date format (DD_MM_YY)
        if not date or not date.replace('_', '').isdigit() or len(date.split('_')) != 3:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected DD_MM_YY (e.g., 04_04_24)")
            
        file_id = ANSWER_KEY_DRIVE_MAP.get(date)
        if not file_id:
            raise ValueError(f"No answer key mapped for date: {date}")
        answer_key = get_answer_key_from_drive(file_id)

        # Process file in memory
        pdf_bytes = await process_file_in_memory(file)

        # Extract MCQ data using BytesIO
        mcq_data = await asyncio.to_thread(extract_mcq_from_pdf, pdf_bytes)

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

        result = {
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
        return result

    except Exception as e:
        print(f"Error processing MCQ: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@app.post("/extract/sa", response_class=JSONResponse)
async def extract_sa(file: UploadFile = File(...), date: str = Form(...)):
    try:
        print(f"Processing SA request - File: {file.filename}, Date: {date}")  # Debug log
        print(f"Received file: {file.filename}")
        print(f"Current directory: {os.getcwd()}")

        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        # Validate date format
        if not date or not date.replace('_', '').isdigit() or len(date.split('_')) != 3:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected DD_MM_YY")

        # Process file in memory
        try:
            pdf_bytes = await process_file_in_memory(file)
            print("File loaded into memory successfully")  # Debug log
        except Exception as e:
            print(f"Error loading file into memory: {str(e)}")  # Debug log
            raise HTTPException(status_code=500, detail=f"Error loading file: {str(e)}")

        # Load answer key
        try:
            file_id = ANSWER_KEY_DRIVE_MAP.get(date)
            if not file_id:
                raise ValueError(f"No answer key mapped for date: {date}")
            answer_key = get_answer_key_from_drive(file_id)
            print(f"Loaded answer key with {len(answer_key)} entries")  # Debug log
        except json.JSONDecodeError as e:
            print(f"Error parsing answer key: {str(e)}")  # Debug log
            raise HTTPException(status_code=500, detail=f"Invalid answer key format: {str(e)}")
        except Exception as e:
            print(f"Error loading answer key: {str(e)}")  # Debug log
            raise HTTPException(status_code=500, detail=f"Error loading answer key: {str(e)}")

        # Extract SA data
        try:
            sa_data = await asyncio.to_thread(extract_sa_from_pdf, pdf_bytes)
            # print(f"Extracted SA data with shape: {sa_data.shape}")  # Debug log
        except Exception as e:
            # print(f"Error extracting SA data: {str(e)}")  # Debug log
            raise HTTPException(status_code=500, detail=f"Error extracting data from PDF: {str(e)}")

        # Process SA answers
        try:
            answer_key_dict = {str(item["id"]): str(item["correct_option"]) for item in answer_key}
            results = []
            total_score = correct_count = incorrect_count = skipped_count = 0

            for _, row in sa_data.iterrows():
                question_id = str(row.get("question_id"))
                given_answer = str(row.get("answer", "")).strip()

                # print(f"Processing question {question_id} with answer: {given_answer}")  # Debug log

                if question_id not in answer_key_dict:
                    # print(f"Question ID {question_id} not found in answer key")  # Debug log
                    continue

                correct_answer = answer_key_dict[question_id]

                if not given_answer or given_answer.upper() == "NULL":
                    skipped_count += 1
                    status = "Not Answered"
                    points = 0
                elif given_answer.lower() == correct_answer.lower():  # Case-insensitive comparison
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

            result = {
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
            return result

        except Exception as e:
            print(f"Error processing answers: {str(e)}")  # Debug log
            raise HTTPException(status_code=500, detail=f"Error processing answers: {str(e)}")

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        print(f"Unexpected error in SA endpoint: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/")
async def root():
    return {"message": "Welcome to the PDF Question Extractor API. Use /extract/mcq or /extract/sa endpoints."}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
