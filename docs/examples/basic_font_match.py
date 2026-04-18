"""Basic font identification from an image."""

import lipi

client = lipi.Client()  # uses LIPI_API_KEY env var or ~/.lipi/config.toml

result = client.font_match("screenshot.png")

print(f"Found {len(result.texts)} text region(s)\n")

for text in result.texts:
    print(f'  "{text.text}"')
    print(f"  Best match:  {text.best_match}")
    print(f"  Commercial:  {', '.join(text.commercial_alternatives)}")
    print(f"  Free:        {', '.join(text.free_alternatives)}")
    print()

# Check remaining credits
credits = client.get_credits()
print(f"Credits remaining: {credits.total_credits}")
