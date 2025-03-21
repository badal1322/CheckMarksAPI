import os
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import tempfile
import uvicorn
from models import extract_mcq_from_pdf, extract_sa_from_pdf

app = FastAPI(title="PDF Question Extractor API", 
              description="API for extracting MCQ and Short Answer questions from PDF files")

@app.post("/extract/mcq", response_class=JSONResponse)
async def extract_mcq(file: UploadFile = File(...)):
    """
    Extract Multiple Choice Questions from a PDF file
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
        
        # Process the PDF using the existing model
        mcq_data = extract_mcq_from_pdf(temp_file.name)
        
        # Convert to JSON-serializable format
        result = mcq_data.to_dict(orient='records')
        
        return {"mcq_data": result, "filename": file.filename}
    
    except Exception as e:
        # Add error handling to provide more useful error messages
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    
    finally:
        # Clean up the temp file
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

@app.post("/extract/sa", response_class=JSONResponse)
async def extract_sa(file: UploadFile = File(...)):
    """
    Extract Short Answer Questions from a PDF file
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
        
        # Process the PDF using the existing model
        sa_data = extract_sa_from_pdf(temp_file.name)
        
        # Convert to JSON-serializable format
        result = sa_data.to_dict(orient='records')
        
        return {"sa_data": result, "filename": file.filename}
    
    except Exception as e:
        # Add error handling to provide more useful error messages
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    
    finally:
        # Clean up the temp file
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

@app.get("/")
async def root():
    return {"message": "Welcome to the PDF Question Extractor API. Use /extract/mcq or /extract/sa endpoints."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 