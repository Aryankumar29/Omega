// === Toast Notifications ===
function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const div = document.createElement('div');
    div.className = `toast toast-${type}`;
    div.innerHTML = `<span>${message}</span><button onclick="this.parentElement.remove()" style="background:none;border:none;color:inherit;cursor:pointer;margin-left:12px">&times;</button>`;
    container.appendChild(div);
    setTimeout(() => div.remove(), 5000);
}

// === Modal ===
function showModal(html) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    content.innerHTML = html;
    overlay.classList.remove('hidden');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('modal-content').innerHTML = '';
}

// Close modal on overlay click
document.getElementById('modal-overlay')?.addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
});

// === Inline Editing ===
document.querySelectorAll('.editable').forEach(cell => {
    cell.addEventListener('dblclick', function() {
        if (this.querySelector('input')) return;
        const field = this.dataset.field;
        const value = this.textContent.trim();
        const row = this.closest('tr');
        const id = row.dataset.id;

        const input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.style.cssText = 'width:100%;padding:4px;background:var(--bg-input);border:1px solid var(--primary);border-radius:4px;color:var(--text);font-size:13px';

        this.textContent = '';
        this.appendChild(input);
        input.focus();
        input.select();

        const save = async () => {
            const newValue = input.value.trim();
            this.textContent = newValue;
            if (newValue !== value) {
                const res = await fetch(`/contacts/${id}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({[field]: newValue})
                });
                if (!res.ok) {
                    this.textContent = value;
                    toast('Failed to update', 'error');
                }
            }
        };

        input.addEventListener('blur', save);
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') { this.parentElement.textContent = value; }
        });
    });
});

// === Keyboard Shortcuts ===
document.addEventListener('keydown', function(e) {
    // Arrow keys in card view
    if (typeof prevEmail !== 'undefined' && typeof nextEmail !== 'undefined') {
        if (e.key === 'ArrowLeft' && !e.target.matches('input,textarea')) prevEmail();
        if (e.key === 'ArrowRight' && !e.target.matches('input,textarea')) nextEmail();
    }
});

// === Utility: Format date ===
function formatDate(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

// === Auto-refresh tracking data ===
if (window.location.pathname.includes('/send')) {
    setInterval(async () => {
        // Light poll for tracking updates
        try {
            const res = await fetch('/send/tracking-updates');
            if (res.ok) {
                const data = await res.json();
                if (data.has_updates) {
                    // Could update specific cells, but for now just show a toast
                    toast('New tracking updates available', 'info');
                }
            }
        } catch (e) { /* silently fail */ }
    }, 30000);
}
