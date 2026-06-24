"""
Custom SageMaker inference handler for all-MiniLM-L6-v2 sentence embeddings.

SageMaker's Hugging Face inference toolkit calls model_fn once at container
startup and predict_fn for every request -- these exact names are the
contract the toolkit expects.

mean_pooling averages per-token embeddings into one sentence vector,
weighted by the attention mask so padding tokens don't skew the result.
This logic has been unit-tested against synthetic padded/unpadded
sequences to confirm padding is correctly excluded from the average.
"""

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel


def mean_pooling(model_output, attention_mask):
    """Average token embeddings into one sentence vector, ignoring padding tokens."""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    summed = torch.sum(token_embeddings * input_mask_expanded, 1)
    counts = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    return summed / counts


def model_fn(model_dir):
    """Called once when the container starts. model_dir is the unpacked model.tar.gz contents."""
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModel.from_pretrained(model_dir)
    model.eval()
    return {"tokenizer": tokenizer, "model": model}


def predict_fn(input_data, model_dict):
    """
    Called for every inference request. input_data is a dict like
    {"inputs": "some text"} or {"inputs": ["text1", "text2"]}.
    """
    tokenizer = model_dict["tokenizer"]
    model = model_dict["model"]

    texts = input_data["inputs"]
    if isinstance(texts, str):
        texts = [texts]

    encoded = tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors="pt")

    with torch.no_grad():
        model_output = model(**encoded)

    embeddings = mean_pooling(model_output, encoded["attention_mask"])
    embeddings = F.normalize(embeddings, p=2, dim=1)  # matches sentence-transformers' default normalization

    return {"embeddings": embeddings.tolist()}
