/* Comportements façon Odoo : lanceur d'applications + panneau de contrôle. */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    //  Lanceur d'applications
    // ------------------------------------------------------------------
    function initHomeMenu() {
        var header = document.getElementById('o_navbar');
        var toggle = document.getElementById('o_menu_toggle');
        var home = document.getElementById('o_home_menu');
        var search = document.getElementById('o_home_search');
        var apps = document.getElementById('o_apps');
        var empty = document.getElementById('o_home_empty');
        if (!header || !toggle || !home) { return; }

        var isHomePage = !home.hidden;      // page /apps/ : le lanceur reste affiché
        var hasApp = !!document.querySelector('.o_menu_sections');

        function open() {
            home.hidden = false;
            header.classList.add('o_home_menu_open');
            document.body.classList.add('o_home_open');
            if (search) { search.value = ''; filter(''); setTimeout(function () { search.focus(); }, 30); }
        }
        function close() {
            if (isHomePage) { return; }
            home.hidden = true;
            header.classList.remove('o_home_menu_open');
            document.body.classList.remove('o_home_open');
        }
        function visibleApps() {
            return Array.prototype.filter.call(apps.querySelectorAll('.o_app'), function (a) { return !a.hidden; });
        }
        function filter(q) {
            q = (q || '').trim().toLowerCase();
            Array.prototype.forEach.call(apps.querySelectorAll('.o_app'), function (a) {
                a.hidden = q && a.getAttribute('data-name').indexOf(q) === -1;
            });
            if (empty) { empty.hidden = visibleApps().length > 0; }
        }

        if (isHomePage) {
            document.body.classList.add('o_home_open');
            if (search && window.matchMedia('(min-width: 768px)').matches) { search.focus(); }
        }

        toggle.addEventListener('click', function () {
            if (isHomePage) { return; }
            if (home.hidden) { open(); } else { close(); }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !home.hidden) { close(); }
        });
        // Clic dans le vide du lanceur → fermeture (hors page d'accueil)
        home.addEventListener('click', function (e) {
            if (e.target === home) { close(); }
        });
        if (search) {
            search.addEventListener('input', function () { filter(search.value); });
            search.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    var first = visibleApps()[0];
                    if (first) { window.location.href = first.getAttribute('href'); }
                } else if (e.key === 'ArrowDown') {
                    var v = visibleApps();
                    if (v.length) { v[0].focus(); e.preventDefault(); }
                }
            });
        }
        // Navigation clavier entre applications
        apps.addEventListener('keydown', function (e) {
            var v = visibleApps();
            var i = v.indexOf(document.activeElement);
            if (i < 0) { return; }
            var next = null;
            if (e.key === 'ArrowRight') { next = v[Math.min(i + 1, v.length - 1)]; }
            else if (e.key === 'ArrowLeft') { next = v[Math.max(i - 1, 0)]; }
            else if (e.key === 'ArrowDown') { next = v[Math.min(i + 6, v.length - 1)]; }
            else if (e.key === 'ArrowUp') { next = v[Math.max(i - 6, 0)]; }
            if (next) { next.focus(); e.preventDefault(); }
        });
        // Les menus des applications se ferment automatiquement quand on ouvre le lanceur
        void hasApp;
    }

    // ------------------------------------------------------------------
    //  Panneau de contrôle : fil d'Ariane + boutons d'action
    //  Le premier titre (h1/h2) de la page devient le dernier élément du fil
    //  d'Ariane ; la rangée qui le contient (boutons d'action) est déplacée
    //  à droite du panneau, comme dans Odoo.
    // ------------------------------------------------------------------
    var HEAVY = 'table, .card, form:not(.d-inline), input:not([type=hidden]), select, textarea, canvas, .list-group, .nav-tabs, img, [class*=hero], [class*=banner]';

    var BANNERS = '.compta-header, .stock-header, .secr-header, [class*=page-header], [class*=-header-bar]';

    function findHeading(root) {
        var hs = root.querySelectorAll('h1, h2, h3, h4');
        for (var i = 0; i < hs.length; i++) {
            var h = hs[i];
            if (h.closest('.card, .modal, table, .alert, form, .o_control_panel, [hidden]') && !h.closest(BANNERS)) { continue; }
            if (!h.textContent.trim()) { continue; }
            // h3/h4 : uniquement dans un bandeau d'en-tête de module
            if ((h.tagName === 'H3' || h.tagName === 'H4') && !h.closest(BANNERS)) { continue; }
            return h;
        }
        return null;
    }

    function cleanText(el) {
        var c = el.cloneNode(true);
        Array.prototype.forEach.call(c.querySelectorAll('i, svg, .badge, small, button, .btn'), function (n) { n.remove(); });
        return c.textContent.replace(/\s+/g, ' ').trim();
    }

    function initControlPanel() {
        var cp = document.getElementById('o_control_panel');
        var content = document.getElementById('o_content');
        if (!cp || !content) { return; }

        var h = findHeading(content);
        var title = h ? cleanText(h) : '';
        var appEl = document.querySelector('.o_menu_brand:not(.o_menu_brand_static)');
        var appName = appEl ? appEl.textContent.trim() : '';
        var appUrl = appEl ? appEl.getAttribute('href') : '';
        var section = (cp.getAttribute('data-section') || '').trim();

        if (!h && !appName) { return; }

        // Candidat à déplacer : le plus grand ancêtre « léger » du titre
        var moved = null;
        if (h) {
            var top = h;
            while (top.parentElement && top.parentElement !== content) {
                var p = top.parentElement;
                if (p.querySelector(HEAVY)) { break; }
                if (p.textContent.trim().length > 160) { break; }
                if (p.querySelectorAll('*').length > 24) { break; }
                if (p.querySelectorAll('h1, h2, h3, h4').length > 1) { break; }
                top = p;
            }
            if (top !== h && !top.querySelector(HEAVY)) { moved = top; }
        }

        // Fil d'Ariane
        var ol = document.createElement('ol');
        ol.className = 'o_breadcrumb';
        function crumb(text, href, active) {
            var li = document.createElement('li');
            if (active) { li.className = 'active'; }
            if (href) {
                var a = document.createElement('a'); a.href = href; a.textContent = text; li.appendChild(a);
            } else { li.textContent = text; }
            ol.appendChild(li);
        }
        function norm(t) { return (t || '').replace(/\s+/g, ' ').trim().toLowerCase(); }
        // Odoo 18 : le nom de l'application est déjà dans la barre du haut ;
        // le fil d'Ariane ne montre que le titre de la page courante.
        var last = title || section;
        if (last && norm(last) !== norm(appName)) { crumb(last, null, true); }
        else if (appName) { crumb(appName, appUrl, true); }
        cp.appendChild(ol);

        if (h) {
            if (moved) {
                var box = document.createElement('div');
                box.className = 'o_cp_buttons';
                h.hidden = true;
                box.appendChild(moved);
                cp.appendChild(box);
                // Retire la sous-description éventuelle si elle est vide après masquage
            } else {
                h.hidden = true;
            }
        }
        cp.hidden = false;
    }


    // ------------------------------------------------------------------
    //  Menus qui ne tiennent pas dans la barre → menu « ⋯ » (comme Odoo)
    // ------------------------------------------------------------------
    function initOverflowMenu() {
        var ul = document.querySelector('.o_menu_sections');
        var wrap = document.getElementById('o_menu_sections');
        if (!ul || !wrap) { return; }
        var items = Array.prototype.slice.call(ul.children);
        var more = document.createElement('li');
        more.className = 'dropdown o_more_menu';
        more.hidden = true;
        more.innerHTML = '<a class="o_nav_entry dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false" title="Plus"><i class="bi bi-three-dots"></i></a>' +
                         '<ul class="dropdown-menu o_dropdown_menu"></ul>';
        ul.appendChild(more);
        var moreList = more.querySelector('ul');

        function fill(hiddenItems) {
            moreList.innerHTML = '';
            hiddenItems.forEach(function (li) {
                var toggle = li.querySelector(':scope > a.dropdown-toggle');
                if (toggle) {
                    var h = document.createElement('li');
                    h.innerHTML = '<h6 class="dropdown-header"></h6>';
                    h.firstChild.textContent = toggle.textContent.trim();
                    moreList.appendChild(h);
                    Array.prototype.forEach.call(li.querySelectorAll(':scope > ul > li'), function (c) {
                        moreList.appendChild(c.cloneNode(true));
                    });
                } else {
                    var a = li.querySelector('a');
                    var l = document.createElement('li');
                    l.innerHTML = '<a class="dropdown-item"></a>';
                    l.firstChild.href = a.getAttribute('href');
                    l.firstChild.textContent = a.textContent.trim();
                    if (a.classList.contains('active')) { l.firstChild.classList.add('active'); }
                    moreList.appendChild(l);
                }
            });
        }

        function layout() {
            items.forEach(function (li) { li.hidden = false; });
            more.hidden = true;
            if (window.innerWidth < 992) { return; }      // mobile : menu hamburger
            var avail = wrap.clientWidth;
            var widths = items.map(function (li) { return li.getBoundingClientRect().width; });
            var total = widths.reduce(function (a, b) { return a + b; }, 0);
            if (total <= avail) { return; }
            var reserve = 46, used = 0, cut = items.length;
            for (var i = 0; i < items.length; i++) {
                if (used + widths[i] > avail - reserve) { cut = i; break; }
                used += widths[i];
            }
            var hiddenItems = items.slice(cut);
            hiddenItems.forEach(function (li) { li.hidden = true; });
            fill(hiddenItems);
            more.hidden = false;
        }
        var t = null;
        window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(layout, 80); });
        layout();
        if (document.fonts && document.fonts.ready) { document.fonts.ready.then(layout); }
    }

    document.addEventListener('DOMContentLoaded', function () {
        initHomeMenu();
        initOverflowMenu();
        initControlPanel();
    });
})();
