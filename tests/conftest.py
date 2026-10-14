"""Pytest fixtures for synthetic data and images."""

import tempfile
from pathlib import Path
from typing import Generator
import pandas as pd
from PIL import Image, ImageDraw
import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory cleaned up after test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_excel_file(temp_dir: Path) -> Path:
    """Create a synthetic Excel spreadsheet with typical ID card columns."""
    file_path = temp_dir / "sample_records.xlsx"
    data = {
        "PIN Number": ["100001", "100002", "  100003  ", "100004", "005001", "100002", ""],
        "Name": ["Aditya Sharma", "Priya Patel", "Rahul Verma", "Sneha Rao", "Ananya Das", "Duplicate User", "No Pin User"],
        "Office Name": ["Headquarters", "Regional Office", "Headquarters", "Tech Hub", "Regional Office", "Branch", "Branch"],
        "Designation": ["Senior Engineer", "Product Manager", "Designer", "Data Scientist", "Analyst", "Engineer", "Intern"],
        "Constituency": ["North Central", "South Coast", "Metro", "East Valley", "West End", "North Central", "Metro"],
        "Source PDF": ["docs/batch1.pdf", "docs/batch1.pdf", "docs/batch2.pdf", "docs/batch2.pdf", "docs/batch3.pdf", "docs/batch1.pdf", "docs/batch1.pdf"],
        "Page": [1, 2, 5, 8, 12, 15, 20],
    }
    df = pd.DataFrame(data)
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Employees", index=False)
        df.to_excel(writer, sheet_name="Contractors", index=False)
    return file_path


@pytest.fixture
def sample_csv_file(temp_dir: Path) -> Path:
    """Create a synthetic CSV file."""
    file_path = temp_dir / "sample_records.csv"
    data = {
        "PIN Number": ["200001", "200002", "009999"],
        "Name": ["John Doe", "Jane Smith", "Bob Wilson"],
        "Designation": ["Officer", "Manager", "Clerk"],
    }
    df = pd.DataFrame(data)
    df.to_csv(file_path, index=False)
    return file_path


@pytest.fixture
def sample_photos_dir(temp_dir: Path) -> Path:
    """Create a directory with synthetic photograph files."""
    photo_dir = temp_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    pins_and_colors = [
        ("100001", "red", ".jpg"),
        ("100002", "blue", ".png"),
        ("100003", "green", ".jpeg"),
        ("005001", "purple", ".webp"),
        ("999999", "orange", ".png"),  # Unassigned photo (no Excel record)
    ]

    for pin, color, ext in pins_and_colors:
        img = Image.new("RGB", (300, 300), color=color)
        draw = ImageDraw.Draw(img)
        draw.text((30, 130), f"Photo {pin}", fill="white")
        img.save(photo_dir / f"{pin}{ext}")

    # Add ambiguous photo for 100004 (both .jpg and .png)
    img1 = Image.new("RGB", (200, 200), color="cyan")
    img1.save(photo_dir / "100004.jpg")
    img2 = Image.new("RGB", (200, 200), color="magenta")
    img2.save(photo_dir / "100004.png")

    return photo_dir
