from pathlib import Path
import base64

# M&G brand palette (approximate from provided artwork)
# Burgundy block background
BRAND_BURGUNDY = "#7A003C"
# Teal/green accent for "AI in SDLC"
BRAND_GREEN = "#19C6B6"


def find_brand_logo_b64() -> str | None:
	"""Return base64 for preferred brand logo image if found.

	Search order favors a new logo named "brand_logo" (png/jpg/webp) and
	falls back to the previous "logoImage.png" if needed.
	"""
	candidates = [
		Path("brand_logo.png"),
		Path("brand_logo.jpg"),
		Path("brand_logo.webp"),
		Path(__file__).parent / "brand_logo.png",
		Path(__file__).parent / "brand_logo.jpg",
		Path(__file__).parent / "brand_logo.webp",
		Path("assets/brand_logo.png"),
		Path("assets/brand_logo.jpg"),
		Path("assets/brand_logo.webp"),
		# Legacy fallback
		Path("logoImage.png"),
		Path(__file__).parent / "logoImage.png",
	]
	for candidate in candidates:
		try:
			if candidate.exists():
				return base64.b64encode(candidate.read_bytes()).decode("utf-8")
		except Exception:
			continue
	return None


def find_flamingo_icon_b64() -> str | None:
	"""Return base64 for an optional flamingo icon image if found.

	Expected names: flamingo_icon.{png|jpg|webp} or flamingo.{png|jpg|webp}
	in repo root, this module's folder, or an assets/ folder.
	"""
	candidates = [
		Path("flamingo_icon.png"), Path("flamingo_icon.jpg"), Path("flamingo_icon.webp"),
		Path("flamingo.png"), Path("flamingo.jpg"), Path("flamingo.webp"),
		Path(__file__).parent / "flamingo_icon.png",
		Path(__file__).parent / "flamingo_icon.jpg",
		Path(__file__).parent / "flamingo_icon.webp",
		Path(__file__).parent / "flamingo.png",
		Path(__file__).parent / "flamingo.jpg",
		Path(__file__).parent / "flamingo.webp",
		Path("assets/flamingo_icon.png"), Path("assets/flamingo_icon.jpg"), Path("assets/flamingo_icon.webp"),
		Path("assets/flamingo.png"), Path("assets/flamingo.jpg"), Path("assets/flamingo.webp"),
	]
	for candidate in candidates:
		try:
			if candidate.exists():
				return base64.b64encode(candidate.read_bytes()).decode("utf-8")
		except Exception:
			continue
	return None

