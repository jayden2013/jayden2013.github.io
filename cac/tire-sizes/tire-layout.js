document.addEventListener("DOMContentLoaded", function() {
    // 1. Inject Styles
    const style = document.createElement('style');
    style.textContent = `
        .bg-dot-pattern {
            background-image: radial-gradient(currentColor 1px, transparent 1px);
            background-size: 24px 24px;
        }
    `;
    document.head.appendChild(style);

    // 1b. Inject AdSense Script (Centralized)
    const adScript = document.createElement('script');
    adScript.async = true;
    adScript.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5978349780180432";
    adScript.crossOrigin = "anonymous";
    document.head.appendChild(adScript);

    // 2. Background & Header Injection
    const bgHTML = `<div class="fixed inset-0 z-0 pointer-events-none text-slate-200 dark:text-slate-900/50 bg-dot-pattern [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_100%)]"></div>`;
    document.body.insertAdjacentHTML("afterbegin", bgHTML);

    const headerHTML = `
    <nav class="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-700 sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <a href="../index.html" class="text-2xl font-black tracking-tighter bg-gradient-to-r from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">TIRE</a>
                </div>
                <div class="flex items-center space-x-4">
                    <a href="../index.html" class="text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors">Home</a>
                </div>
            </div>
        </div>
    </nav>`;
    document.body.insertAdjacentHTML("afterbegin", headerHTML);

    // 3. About Section & AdSense Injection
    const aboutEl = document.getElementById("tire-about");
    if (aboutEl) {
        const ymm = aboutEl.getAttribute("data-ymm") || "your vehicle";
        
        // Inject AdSense before About
        const adsenseHTML = `
        <div class="my-8 text-center overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-900/50 p-4">
            <span class="text-xs text-slate-400 uppercase tracking-wider mb-2 block">Advertisement</span>
            <ins class="adsbygoogle"
                 style="display:block"
                 data-ad-client="ca-pub-5978349780180432"
                 data-ad-slot="3728400476"
                 data-ad-format="auto"
                 data-full-width-responsive="true"></ins>
        </div>`;
        aboutEl.insertAdjacentHTML("beforebegin", adsenseHTML);
        
        // Initialize AdSense
        try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}

        aboutEl.innerHTML = `
        <div class="bg-white dark:bg-slate-800/50 backdrop-blur-sm rounded-2xl p-8 border border-slate-200 dark:border-slate-700 shadow-sm">
            <h2 class="text-2xl font-bold mb-4 flex items-center text-slate-900 dark:text-white"><i class="bi bi-info-circle text-emerald-500 mr-3"></i>About Factory Specs</h2>
            <p class="text-slate-600 dark:text-slate-400 leading-relaxed">The tire specifications listed here are for the original equipment (OE) tires installed on the ${ymm} at the factory. Vehicle manufacturers often collaborate with tire brands to develop tires optimized for the specific performance characteristics of the vehicle. <br><br><strong class="text-slate-800 dark:text-slate-200">Important:</strong> Always verify the tire size, load index, and speed rating listed on your vehicle's tire placard (typically located on the driver's side door jamb) before purchasing new tires.</p>
        </div>`;
    }

    // 4. Footer Injection
    const footerHTML = `
    <footer class="bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 mt-auto py-8 z-10">
        <div class="container mx-auto px-4 text-center text-slate-500 dark:text-slate-400 text-sm">
            <p>&copy; ${new Date().getFullYear()} Cars & Collectibles. All rights reserved.</p>
            <p class="mt-2">Data provided for informational purposes only. Always consult your owner's manual.</p>
        </div>
    </footer>`;
    document.body.insertAdjacentHTML("beforeend", footerHTML);
});