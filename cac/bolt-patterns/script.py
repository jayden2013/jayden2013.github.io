# c:\Users\Jayden\Documents\jayden2013.github.io\bolt-patterns\generate_seo_pages.py

import csv
import os
import shutil
import re

# Configuration
CSV_FILE = 'bolt-patterns.csv'
OUT_DIR = 'vehicles'
BASE_URL = 'https://www.carsandcollectibles.com/bolt-patterns/vehicles/'

# Template Parts
TEMPLATE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <link rel="canonical" href="{canonical_url}" />
  <link rel="icon" href="../../favicon.ico" type="image/x-icon" />
  
  <!-- Open Graph -->
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="{canonical_url}" />
  <meta property="og:site_name" content="Cars & Collectibles" />
  <meta property="og:image" content="https://www.carsandcollectibles.com/images/hero-car.jpg" />
  
  <!-- AdSense -->
  <meta name="google-adsense-account" content="ca-pub-5978349780180432">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5978349780180432" crossorigin="anonymous"></script>
  
  <!-- Structured Data (Breadcrumbs) -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{
        "@type": "ListItem",
        "position": 1,
        "name": "Home",
        "item": "https://www.carsandcollectibles.com/"
      }},
      {{
        "@type": "ListItem",
        "position": 2,
        "name": "Bolt Patterns",
        "item": "https://www.carsandcollectibles.com/bolt-patterns/"
      }},
      {{
        "@type": "ListItem",
        "position": 3,
        "name": "Vehicles",
        "item": "https://www.carsandcollectibles.com/bolt-patterns/vehicles/index.html"
      }}{json_ld_items}
    ]
  }}
  </script>

  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{ extend: {{ colors: {{ emerald: {{ 400: '#34d399', 500: '#10b981', 600: '#059669' }}, slate: {{ 850: '#151f32', 900: '#0f172a' }} }} }} }}
    }}
  </script>
</head>
<body class="bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 font-sans min-h-screen flex flex-col">
  <div class="max-w-3xl mx-auto w-full px-4 py-8 flex-1">
    <!-- Breadcrumb -->
    <nav class="text-sm text-slate-500 mb-8 overflow-x-auto whitespace-nowrap">
      <a href="../../index.html" class="hover:text-emerald-500">Home</a>
      <span class="mx-2">/</span>
      <a href="../index.html" class="hover:text-emerald-500">Bolt Patterns</a>
      <span class="mx-2">/</span>
      <a href="index.html" class="hover:text-emerald-500">Vehicles</a>
      {breadcrumbs}
    </nav>
"""

TEMPLATE_AD = """
    <div class="my-8 py-4 flex justify-center bg-slate-100 dark:bg-slate-900 rounded-xl overflow-hidden">
        <!-- BOLT Content Ad -->
        <ins class="adsbygoogle"
             style="display:block; min-width: 300px; width: 100%;"
             data-ad-client="ca-pub-5978349780180432"
             data-ad-slot="3728400476"
             data-ad-format="auto"
             data-full-width-responsive="true"></ins>
        <script>
             (adsbygoogle = window.adsbygoogle || []).push({});
        </script>
    </div>
"""

TEMPLATE_FOOTER = """
    <div class="mt-12 pt-8 border-t border-slate-200 dark:border-slate-800 text-center">
      <a href="../index.html" class="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-full font-bold transition-colors">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        Search Another Vehicle
      </a>
      <p class="mt-8 text-xs text-slate-400">
        &copy; <script>document.write(new Date().getFullYear())</script> Cars & Collectibles. All rights reserved.
      </p>
    </div>
  </div>
</body>
</html>
"""

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')

def main():
    # 1. Read Data
    data = []
    if not os.path.exists(CSV_FILE):
        print(f"Error: {CSV_FILE} not found.")
        return

    with open(CSV_FILE, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        next(reader, None) # Skip header
        for row in reader:
            if len(row) < 6: continue
            data.append({
                'year': row[0].strip(),
                'make': row[1].strip(),
                'model': row[2].strip(),
                'submodel': row[3].strip(),
                'metric': row[4].strip(),
                'standard': row[5].strip(),
                'count': row[6].strip() if len(row) > 6 else '',
                'circle': row[7].strip() if len(row) > 7 else ''
            })

    # 2. Prepare Output Directory
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

    # 3. Group Data
    tree = {} # { Make: { Model: [rows] } }
    for item in data:
        mk = item['make']
        md = item['model']
        if not mk or not md: continue
        if mk not in tree: tree[mk] = {}
        if md not in tree[mk]: tree[mk][md] = []
        tree[mk][md].append(item)

    # 4. Generate Make/Model Pages
    for make, models in tree.items():
        make_slug = slugify(make)
        make_filename = f"{make_slug}.html"
        make_url = BASE_URL + make_filename
        
        # JSON-LD for Make Page
        make_json_ld = f""",
      {{
        "@type": "ListItem",
        "position": 4,
        "name": "{make}",
        "item": "{make_url}"
      }}"""

        # Generate Make Index Page
        make_html = TEMPLATE_HEAD.format(
            title=f"{make} Bolt Patterns & Wheel Specs",
            description=f"Browse all {make} models to find bolt patterns, offset, and wheel fitment data.",
            canonical_url=make_url,
            json_ld_items=make_json_ld,
            breadcrumbs=f'<span class="mx-2">/</span> <span class="text-slate-800 dark:text-white font-bold">{make}</span>'
        )
        make_html += f'<h1 class="text-3xl font-bold mb-6">{make} Models</h1><div class="grid grid-cols-1 sm:grid-cols-2 gap-4">'
        
        for model, rows in models.items():
            model_slug = slugify(model)
            filename = f"{make_slug}-{model_slug}.html"
            model_url = BASE_URL + filename
            
            # Link in Make Index
            make_html += f'<a href="{filename}" class="block p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl hover:border-emerald-500 transition-colors font-medium">{model}</a>'

            # --- Generate Model Data Sheet ---
            rows.sort(key=lambda x: x['year'], reverse=True)
            
            years = [r['year'] for r in rows if r['year'].isdigit()]
            year_str = f"{min(years)}-{max(years)}" if years else "All Years"
            
            patterns = set(f"{r['metric']} ({r['standard']})" for r in rows)
            pattern_str = ", ".join(patterns)

            page_title = f"{make} {model} Bolt Pattern & Wheel Specs ({year_str})"
            desc = f"Find {make} {model} bolt pattern, offset, center bore, and lug nut specs. Complete data for {year_str} models. Pattern: {pattern_str}."

            # JSON-LD for Model Page
            model_json_ld = f""",
      {{
        "@type": "ListItem",
        "position": 4,
        "name": "{make}",
        "item": "{make_url}"
      }},
      {{
        "@type": "ListItem",
        "position": 5,
        "name": "{model}",
        "item": "{model_url}"
      }}"""

            model_html = TEMPLATE_HEAD.format(
                title=page_title,
                description=desc,
                canonical_url=model_url,
                json_ld_items=model_json_ld,
                breadcrumbs=f'<span class="mx-2">/</span> <a href="{make_slug}.html" class="hover:text-emerald-500">{make}</a> <span class="mx-2">/</span> <span class="text-slate-800 dark:text-white font-bold">{model}</span>'
            )

            model_html += f"""
            <header class="mb-8">
                <h1 class="text-3xl md:text-4xl font-black text-slate-900 dark:text-white mb-2">{make} {model}</h1>
                <p class="text-xl text-emerald-600 dark:text-emerald-400">{pattern_str}</p>
            </header>

            <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden mb-8">
                <table class="w-full text-left border-collapse">
                    <thead class="bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
                        <tr>
                            <th class="p-4 font-semibold text-sm text-slate-500 uppercase">Year</th>
                            <th class="p-4 font-semibold text-sm text-slate-500 uppercase">Submodel</th>
                            <th class="p-4 font-semibold text-sm text-slate-500 uppercase">Pattern (Metric)</th>
                            <th class="p-4 font-semibold text-sm text-slate-500 uppercase">Pattern (Std)</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 dark:divide-slate-700">
            """
            
            for r in rows:
                model_html += f"""
                <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <td class="p-4 font-bold">{r['year']}</td>
                    <td class="p-4 text-slate-600 dark:text-slate-400">{r['submodel']}</td>
                    <td class="p-4 font-mono text-emerald-600 dark:text-emerald-400">{r['metric']}</td>
                    <td class="p-4 font-mono text-slate-600 dark:text-slate-400">{r['standard']}</td>
                </tr>
                """
            
            model_html += """
                    </tbody>
                </table>
            </div>
            """

            # Insert Explicit Ad Unit
            model_html += TEMPLATE_AD
            
            model_html += """
            <div class="prose dark:prose-invert max-w-none">
                <h3>Fitment Notes</h3>
                <p>The <strong>{make} {model}</strong> uses a <strong>{pattern}</strong> bolt pattern. This is also known as the <strong>PCD</strong> (Pitch Circle Diameter). When shopping for aftermarket wheels, ensure the center bore matches or is larger than the vehicle's hub. If the wheel bore is larger, hub centric rings are recommended to prevent vibration.</p>
                <p><strong>Lug Hardware:</strong> Always use the correct lug nuts or lug bolts for your specific vehicle year. Torque them to the manufacturer's specified setting.</p>
            </div>
            """.format(make=make, model=model, pattern=pattern_str.split(',')[0])

            model_html += TEMPLATE_FOOTER
            
            with open(os.path.join(OUT_DIR, filename), 'w', encoding='utf-8') as f:
                f.write(model_html)

        make_html += "</div>" + TEMPLATE_FOOTER
        with open(os.path.join(OUT_DIR, make_filename), 'w', encoding='utf-8') as f:
            f.write(make_html)

    # 5. Generate Main Index (vehicles/index.html)
    index_url = BASE_URL + "index.html"
    index_html = TEMPLATE_HEAD.format(
        title="Vehicle Bolt Pattern Directory",
        description="Browse bolt patterns by vehicle make and model.",
        canonical_url=index_url,
        json_ld_items="", # No extra breadcrumbs for index
        breadcrumbs=""
    )
    index_html += '<h1 class="text-3xl font-bold mb-6">Browse by Make</h1><div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">'
    
    for make in sorted(tree.keys()):
        slug = slugify(make)
        index_html += f'<a href="{slug}.html" class="block p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl hover:border-emerald-500 hover:shadow-md transition-all text-center font-bold">{make}</a>'
    
    index_html += "</div>" + TEMPLATE_AD + TEMPLATE_FOOTER
    with open(os.path.join(OUT_DIR, "index.html"), 'w', encoding='utf-8') as f:
        f.write(index_html)

    print(f"Successfully generated {len(tree)} make pages and {sum(len(m) for m in tree.values())} model pages in '{OUT_DIR}/'.")

if __name__ == "__main__":
    main()
