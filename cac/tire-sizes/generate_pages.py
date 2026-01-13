import csv
import os
import re
from datetime import datetime

# Configuration
CSV_FILE = 'factory_tire_sizes.csv'
OUTPUT_DIR = 'vehicle-pages'

def slugify(text):
    """Converts text to a slug suitable for filenames."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def generate_html(year, make, model, trims_data):
    """Generates the HTML content for a specific vehicle page."""
    title = f"{year} {make} {model} Tire Sizes & Factory Specs"
    description = f"Find factory tire sizes, load indices, and speed ratings for the {year} {make} {model}. View original equipment tire specifications for all trims."
    keywords = f"{year} {make} {model} tire size, {make} {model} tires, factory tire size {model}, {make} tire specs, {year} {make} {model} load index"
    
    # Sort trims by name for consistent display
    trims_data.sort(key=lambda x: x['trim'])
    
    # Generate grid items for each trim
    grid_items = ""
    for row in trims_data:
        trim_name = row['trim']
        tire_size = row['tireSize']
        load_index = row['loadIndex']
        speed_rating = row['speedRating']
        position = row['tirePosition']
        
        pos_display = ""
        if position and position.lower() != 'both':
             pos_display = f'<span class="text-xs font-semibold px-2 py-1 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 ml-2">{position}</span>'

        grid_items += f"""
            <div class="group bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-6 hover:shadow-lg hover:border-emerald-500/30 transition-all duration-300 relative overflow-hidden">
                <div class="flex justify-between items-start mb-4">
                    <div>
                        <h3 class="text-lg font-bold text-slate-900 dark:text-white">{trim_name}</h3>
                        {pos_display}
                    </div>
                </div>
                
                <div class="mb-4">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Tire Size</div>
                    <div class="text-3xl font-mono font-bold text-emerald-600 dark:text-emerald-400 tracking-tight">{tire_size}</div>
                </div>
                
                <div class="grid grid-cols-2 gap-4 border-t border-slate-100 dark:border-slate-700 pt-4">
                    <div>
                        <div class="text-xs text-slate-500 dark:text-slate-400">Load Index</div>
                        <div class="font-semibold text-slate-700 dark:text-slate-200">{load_index}</div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-500 dark:text-slate-400">Speed Rating</div>
                        <div class="font-semibold text-slate-700 dark:text-slate-200">{speed_rating}</div>
                    </div>
                </div>
            </div>"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="Cars & Collectibles">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:type" content="website">
    
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="../tire-config.js"></script>
    <script src="../tire-layout.js" defer></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
</head>
<body class="bg-slate-50 dark:bg-slate-900 min-h-screen flex flex-col font-sans text-slate-900 dark:text-slate-100">

    <main class="flex-grow container mx-auto px-4 py-12 max-w-7xl relative z-10">
        <nav class="flex mb-8 text-sm text-slate-500 dark:text-slate-400" aria-label="Breadcrumb">
            <ol class="inline-flex items-center space-x-1 md:space-x-2">
                <li class="inline-flex items-center"><a href="../index.html" class="hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors">Home</a></li>
                <li><span class="mx-2">/</span></li>
                <li class="font-medium text-slate-800 dark:text-slate-200">{year} {make} {model}</li>
            </ol>
        </nav>
        <div class="text-center mb-16">
            <h1 class="text-4xl md:text-6xl font-black tracking-tight mb-4 text-slate-900 dark:text-white">{year} {make} {model} <span class="text-emerald-500">Tire Sizes</span></h1>
            <p class="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">Factory original equipment (OE) tire specifications.</p>
            <div class="mt-4">
                <a href="mailto:support@carsandcollectibles.com?subject=Issue Report: {year} {make} {model}" class="text-sm text-slate-400 hover:text-red-500 transition-colors inline-flex items-center gap-1">
                    <i class="bi bi-flag"></i> Report Issue
                </a>
            </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
            {grid_items}
        </div>

        <div id="tire-about" data-ymm="{year} {make} {model}"></div>
    </main>
</body>
</html>"""

    # Minify HTML: Remove newlines and excessive whitespace
    minified_html = re.sub(r'\s+', ' ', html_content).strip()
    return minified_html

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    vehicles = {}
    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                key = (row['year'], row['make'], row['model'])
                if key not in vehicles: vehicles[key] = []
                vehicles[key].append(row)
    except FileNotFoundError:
        print(f"Error: {CSV_FILE} not found.")
        return

    print(f"Found {len(vehicles)} unique vehicles. Generating pages...")
    for (year, make, model), trims in vehicles.items():
        html = generate_html(year, make, model, trims)
        filename = f"{slugify(year)}-{slugify(make)}-{slugify(model)}-tires.html"
        with open(os.path.join(OUTPUT_DIR, filename), 'w', encoding='utf-8') as f: f.write(html)
    print(f"Successfully generated {len(vehicles)} pages in '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    main()