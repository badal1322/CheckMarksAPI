import os
import json
import asyncio
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn
import pandas as pd
from models import extract_mcq_from_pdf, extract_sa_from_pdf

app = FastAPI(title="PDF Question Extractor API", 
              description="API for extracting MCQ and Short Answer questions from PDF files")

logger = logging.getLogger(__name__)

async def save_temp_file(file: UploadFile):
    """Save uploaded file to a temporary location asynchronously."""
    contents = await file.read()
    print("File signature:", contents[:10])
    os.makedirs("temp_uploads", exist_ok=True)
    temp_path = os.path.join("temp_uploads", file.filename)
    with open(temp_path, "wb") as f:
        f.write(contents)
    return temp_path

@app.post("/extract/mcq", response_class=JSONResponse)
async def extract_mcq(file: UploadFile = File(...), answer_key_path: str = "answer_key.json"):
    """Extract MCQs and calculate scores."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    if not os.path.exists(answer_key_path):
        raise HTTPException(status_code=400, detail="Answer key file not found")

    temp_path = await save_temp_file(file)
    file.file.seek(0)
    
    try:
        # Process the PDF asynchronously
        mcq_data = await asyncio.to_thread(extract_mcq_from_pdf, temp_path)
        if not isinstance(mcq_data, pd.DataFrame):
            raise HTTPException(status_code=500, detail="MCQ extraction failed")

        # Load answer key
        with open(answer_key_path, 'r') as f:
            answer_key = json.load(f)
        
        answer_key_dict = {item["question_id"]: item["correct_option_id"] for item in answer_key}

        correct_count = incorrect_count = skipped_count = total_score = 0
        mcq_result = []

        for _, row in mcq_data.iterrows():
            question_id = row.get("question_id")
            chosen_option_id = row.get("chosen_option_id", "")

            if question_id not in answer_key_dict:
                continue

            if not chosen_option_id:
                skipped_count += 1
            elif chosen_option_id == answer_key_dict[question_id]:
                correct_count += 1
                total_score += 4
            else:
                incorrect_count += 1
                total_score -= 1

            mcq_result.append(row.to_dict())

        os.remove(temp_path)  # Clean up temp file

        return {
            "mcq_data": mcq_result,
            "filename": file.filename,
            "score_summary": {
                "correct_questions": correct_count,
                "incorrect_questions": incorrect_count,
                "skipped_questions": skipped_count,
                "total_questions": len(mcq_data),
                "total_score": total_score,
                "scoring_system": "+4 for correct, -1 for incorrect, 0 for skipped"
            }
        }
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.post("/extract/sa", response_class=JSONResponse)
async def extract_sa(file: UploadFile = File(...)):
    """Extract Short Answer Questions asynchronously."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    temp_path = await save_temp_file(file)
    file.file.seek(0)

    try:
        sa_data = await asyncio.to_thread(extract_sa_from_pdf, temp_path)
        if not isinstance(sa_data, pd.DataFrame):
            raise HTTPException(status_code=500, detail="Short answer extraction failed")

        os.remove(temp_path)  # Clean up temp file

        return {
            "sa_data": sa_data.to_dict(orient='records'),
            "filename": file.filename
        }
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Welcome to the PDF Question Extractor API. Use /extract/mcq or /extract/sa endpoints."}

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, workers=4, reload=True)