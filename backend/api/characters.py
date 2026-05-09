from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from agents.loader import list_characters, load_character, save_character, delete_character

router = APIRouter()

class CharacterCreate(BaseModel):
    char_type: str
    name: str
    content: str

class CharacterUpdate(BaseModel):
    content: str

@router.get("")
async def get_characters(char_type: Optional[str] = None):
    return list_characters(char_type)

@router.get("/{char_type}/{char_name}")
async def get_character(char_type: str, char_name: str):
    try:
        return load_character(char_type, char_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Character not found")

@router.post("")
async def create_character(body: CharacterCreate):
    char = save_character(body.char_type, body.name, body.content)
    return char

@router.put("/{char_type}/{char_name}")
async def update_character(char_type: str, char_name: str, body: CharacterUpdate):
    try:
        char = save_character(char_type, char_name, body.content)
        return char
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{char_type}/{char_name}")
async def remove_character(char_type: str, char_name: str):
    ok = delete_character(char_type, char_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"ok": True}
