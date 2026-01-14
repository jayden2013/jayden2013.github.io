import os
import datetime

# Configuration
# The base URL for the vehicle pages
BASE_URL = "https://www.carsandcollectibles.com/tire-sizes/vehicle-pages/"
# The directory containing the generated HTML files (relative to this script)
SEARCH_DIR = "vehicle-pages" 
OUTPUT_FILE = "sitemap.xml"

def main():
    # Determine absolute path to the vehicles directory based on script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    vehicles_dir = os.path.join(script_dir, SEARCH_DIR)
    output_path = os.path.join(script_dir, OUTPUT_FILE)

    if not os.path.exists(vehicles_dir):
        print(f"Error: Directory not found at {vehicles_dir}")
        print("Make sure you run generate_pages.py first!")
        return

    urls = []
    
    print(f"Scanning {vehicles_dir} for HTML files...")

    for root, _, files in os.walk(vehicles_dir):
        for file in files:
            if file.endswith(".html"):
                # Calculate relative path from vehicles dir
                rel_path = os.path.relpath(os.path.join(root, file), vehicles_dir)
                # Convert backslashes to forward slashes for URL (Windows fix)
                url_path = rel_path.replace("\\", "/")
                
                # Construct full URL
                full_url = BASE_URL + url_path
                
                # Get last modified time for the <lastmod> tag
                filepath = os.path.join(root, file)
                mtime = os.path.getmtime(filepath)
                lastmod = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                
                urls.append((full_url, lastmod))

    # Sort URLs alphabetically
    urls.sort()

    # Write the XML file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        
        # Add the main tire sizes index manually
        f.write('  <url>\n')
        f.write(f'    <loc>https://www.carsandcollectibles.com/tire-sizes/index.html</loc>\n')
        f.write(f'    <lastmod>{datetime.date.today().isoformat()}</lastmod>\n')
        f.write('  </url>\n')

        for url, lastmod in urls:
            f.write('  <url>\n')
            f.write(f'    <loc>{url}</loc>\n')
            f.write(f'    <lastmod>{lastmod}</lastmod>\n')
            f.write('  </url>\n')
        f.write('</urlset>')

    print(f"Successfully generated {OUTPUT_FILE} with {len(urls) + 1} URLs.")
    print(f"File saved to: {output_path}")

if __name__ == "__main__":
    main()