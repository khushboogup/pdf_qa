import os
import uuid
import fitz
import hashlib
from django.shortcuts import render, redirect
from django.conf import settings
from .forms import PDFUploadForm, QuestionForm
from supabase import create_client
from sentence_transformers import SentenceTransformer
from huggingface_hub import InferenceClient

# Load secrets from settings.py or environment
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
HF_TOKEN = settings.HF_TOKEN

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = SentenceTransformer('all-MiniLM-L6-v2')
hf_client = InferenceClient(api_key=HF_TOKEN)

# ===== Functions =====
def hash_pdf(pdf_path):
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def extract_and_chunk(pdf_path, chunk_size=500):
    doc = fitz.open(pdf_path)
    text = " ".join([page.get_text() for page in doc])
    words = text.split()
    return [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]

def embed_chunks(chunks):
    return model.encode(chunks, batch_size=16, show_progress_bar=False).tolist()

def store_to_supabase(chunks, embeddings, pdf_id):
    data = [{
        "id": str(uuid.uuid4()),
        "pdf_id": pdf_id,
        "text": chunk,
        "embedding": embedding
    } for chunk, embedding in zip(chunks, embeddings)]
    supabase.table("documents1").upsert(data).execute()

def retrieve_chunks(query, pdf_id, top_k=3):
    query_embedding = model.encode(query).tolist()
    response = supabase.rpc("match_documents", {
        "query_embedding": query_embedding,
        "match_count": top_k,
        "pdf_id_filter": pdf_id
    }).execute()
    return [row["text"] for row in response.data] if response.data else []

def refine_with_llm(chunks, question):
    context = "\n\n---\n\n".join(chunks)
    prompt = f"""
Answer the user's question based on the document chunks below.
Explain simply and accurately.

Chunks:
{context}

Question:
{question}
"""
    response = hf_client.chat.completions.create(
        model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=500
    )
    return response.choices[0].message.content

# ===== Views =====
def upload_pdf(request):
    if request.method == "POST":
        form = PDFUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = request.FILES["pdf_file"]
            pdf_path = os.path.join(settings.MEDIA_ROOT, f"temp_{uuid.uuid4().hex}.pdf")
            with open(pdf_path, "wb") as f:
                for chunk in pdf_file.chunks():
                    f.write(chunk)

            pdf_id = hash_pdf(pdf_path)
            existing = supabase.table("documents1").select("id").eq("pdf_id", pdf_id).execute()
            if not existing.data:
                chunks = extract_and_chunk(pdf_path)
                embeddings = embed_chunks(chunks)
                store_to_supabase(chunks, embeddings, pdf_id)
            
            os.remove(pdf_path)
            request.session["pdf_id"] = pdf_id
            return redirect("ask_question")
    else:
        form = PDFUploadForm()
    return render(request, "upload.html", {"form": form})

def ask_question(request):
    pdf_id = request.session.get("pdf_id")
    answer = None
    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.cleaned_data["question"]
            results = retrieve_chunks(question, pdf_id)
            if results:
                answer = refine_with_llm(results, question)
    else:
        form = QuestionForm()
    return render(request, "question.html", {"form": form, "answer": answer})
