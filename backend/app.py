from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Test API!"} 

# query endpoint
@app.post("/query")
def query(query: str):
    return {"message": "Query received!"}

# upload endpoint
@app.post("/upload")
def upload(file: UploadFile = File(...)):
    return {"message": "File uploaded!"}


