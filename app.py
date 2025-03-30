import os
import json
import asyncio
import tempfile
from fastapi import FastAPI, File, UploadFile, HTTPException
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


@app.post("/extract/mcq", response_class=JSONResponse)
async def extract_mcq(file: UploadFile = File(...), answer_key_path: str = "answer_key.json"):
    """Extract Multiple Choice Questions from a PDF file and calculate scores"""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    if not os.path.exists(answer_key_path):
        raise HTTPException(status_code=400, detail="Answer key file not found")

    temp_file_path = await save_temp_file(file)
    
    try:
        mcq_data = await asyncio.to_thread(extract_mcq_from_pdf, temp_file_path)

        # Load answer key safely
        try:
            with open(answer_key_path, "r") as f:
                json_content = f.read()
                json_content = json_content[:json_content.rindex("]") + 1] if "]" in json_content else json_content
                answer_key = json.loads(json_content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error loading answer key: {str(e)}")

        answer_key_dict = {item["question_id"]: item["correct_option_id"] for item in answer_key}

        correct_count = incorrect_count = skipped_count = total_score = 0

        for _, row in mcq_data.iterrows():
            question_id = row.get("question_id")
            chosen_option_id = row.get("chosen_option_id")

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
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        os.remove(temp_file_path)


@app.post("/extract/sa", response_class=JSONResponse)
async def extract_sa(file: UploadFile = File(...)):
    """Extract Short Answer Questions from a PDF file"""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    temp_file_path = await save_temp_file(file)

    try:
        sa_data = await asyncio.to_thread(extract_sa_from_pdf, temp_file_path)
        return {"sa_data": sa_data.to_dict(orient="records"), "filename": file.filename}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        os.remove(temp_file_path)


@app.get("/")
async def root():
    return {"message": "Welcome to the PDF Question Extractor API. Use /extract/mcq or /extract/sa endpoints."}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)