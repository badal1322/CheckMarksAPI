import os
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import tempfile
import uvicorn
from models import extract_mcq_from_pdf, extract_sa_from_pdf

app = FastAPI(title="PDF Question Extractor API", 
              description="API for extracting MCQ and Short Answer questions from PDF files")

@app.post("/extract/mcq", response_class=JSONResponse)
async def extract_mcq(file: UploadFile = File(...), answer_key_path: str = "answer_key.json"):
    """
    Extract Multiple Choice Questions from a PDF file and calculate scores
    """
    # Validate file is a PDF
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Validate answer key exists
    if not os.path.exists(answer_key_path):
        raise HTTPException(status_code=400, detail="Answer key file not found")
    
    # Save uploaded file temporarily
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    try:
        contents = await file.read()
        temp_file.write(contents)
        temp_file.close()
        
        # Process the PDF using the existing model
        mcq_data = extract_mcq_from_pdf(temp_file.name)
        
        # Load answer key with robust error handling
        try:
            with open(answer_key_path, 'r') as f:
                json_content = f.read()
                # Find the proper JSON ending and trim any extra content
                if ']' in json_content:
                    json_content = json_content[:json_content.rindex(']')+1]
                answer_key = json.loads(json_content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error loading answer key: {str(e)}")
        
        # Convert answer key to dictionary for easier lookup
        answer_key_dict = {item["question_id"]: item["correct_option_id"] for item in answer_key}
        
        # Count correct, incorrect, and skipped questions
        correct_count = 0
        incorrect_count = 0
        skipped_count = 0
        total_score = 0
        
        # Compare student answers with answer key
        for _, row in mcq_data.iterrows():
            question_id = row.get("question_id")
            chosen_option_id = row.get("chosen_option_id")
            
            # Skip if question not in answer key
            if question_id not in answer_key_dict:
                continue
                
            # Check if question was skipped (no chosen option)
            if not chosen_option_id or chosen_option_id == "":
                skipped_count += 1
                # No points for skipped questions
            # Check if answer is correct
            elif chosen_option_id == answer_key_dict[question_id]:
                correct_count += 1
                total_score += 4  # +4 points for correct answer
            # Otherwise, answer is incorrect
            else:
                incorrect_count += 1
                total_score -= 1  # -1 point for incorrect answer
        
        # Convert MCQ data to JSON-serializable format
        mcq_result = mcq_data.to_dict(orient='records')
        
        # Return both the extracted data and the score summary
        return {
            "mcq_data": mcq_result, 
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
        # Add error handling to provide more useful error messages
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    
    finally:
        # Clean up the temp file
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

@app.post("/extract/sa", response_class=JSONResponse)
async def extract_sa(file: UploadFile = File(...), answer_key_path: str = "answer_key.json"):
    """
    Extract Short Answer Questions from a PDF file and calculate scores
    """
    # Validate file is a PDF
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Validate answer key exists
    if not os.path.exists(answer_key_path):
        raise HTTPException(status_code=400, detail="Answer key file not found")
    
    # Save uploaded file temporarily
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    try:
        contents = await file.read()
        temp_file.write(contents)
        temp_file.close()
        
        # Process the PDF using the existing model
        sa_data = extract_sa_from_pdf(temp_file.name)
        
        # Load answer key
        with open(answer_key_path, 'r') as f:
            answer_key = json.loads(f.read())
        
        # Convert answer key to dictionary for easier lookup
        answer_key_dict = {item["question_id"]: item["correct_option_id"] for item in answer_key}
        
        # Initialize counters
        correct_count = 0
        incorrect_count = 0
        unattempted_count = 0
        total_score = 0
        question_details = []

        # Debug total questions
        print(f"Total SA questions found: {len(sa_data)}")
        
        # Compare student answers with answer key
        for _, row in sa_data.iterrows():
            question_id = str(row.get("question_id"))
            given_answer = str(row.get("answer")).strip()
            
            # Skip if question not in answer key
            if question_id not in answer_key_dict:
                continue
            
            correct_answer = str(answer_key_dict[question_id]).strip()
            
            # Create question detail
            question_detail = {
                "question_id": question_id,
                "given_answer": given_answer,
                "correct_answer": correct_answer
            }
            
            # Debug print current question
            print(f"Processing Q{question_id}: Given='{given_answer}' vs Correct='{correct_answer}'")
            
            # Check if NULL or empty answer
            if given_answer.upper() == "NULL" or not given_answer:
                unattempted_count += 1
                question_detail["status"] = "unattempted"
                question_detail["points"] = 0
            
            # Check exact match with correct answer
            elif given_answer == correct_answer:
                correct_count += 1
                total_score += 4
                question_detail["status"] = "correct"
                question_detail["points"] = 4
            
            # Answer doesn't match
            else:
                incorrect_count += 1
                total_score -= 1
                question_detail["status"] = "incorrect"
                question_detail["points"] = -1
            
            question_details.append(question_detail)
            
            # Debug print running totals
            print(f"Running totals - Correct: {correct_count}, Incorrect: {incorrect_count}, Unattempted: {unattempted_count}")

        # Return response with detailed counts
        return {
            "filename": file.filename,
            "score_summary": {
                "correct_questions": correct_count,
                "incorrect_questions": incorrect_count,
                "unattempted_questions": unattempted_count,
                "total_questions": correct_count + incorrect_count + unattempted_count,
                "total_score": total_score,
                "scoring_scheme": "+4 correct, -1 incorrect, 0 unattempted"
            },
            "question_details": question_details,
            "sa_data": sa_data.to_dict(orient='records')
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

@app.get("/")
async def root():
    return {"message": "Welcome to the PDF Question Extractor API. Use /extract/mcq or /extract/sa endpoints."}

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)