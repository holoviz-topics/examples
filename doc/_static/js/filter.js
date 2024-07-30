document.addEventListener('DOMContentLoaded', function () {
    const buttons = document.querySelectorAll('.filter-btn');
    const cards = document.querySelectorAll('.sd-card');

    buttons.forEach(button => {
        button.addEventListener('click', function () {
            // Toggle the custom active class on the clicked button
            this.classList.toggle('filter-btn-active');

            // Determine active labels
            let activeLabels = Array.from(buttons)
                                    .filter(btn => btn.classList.contains('filter-btn-active'))
                                    .map(btn => btn.getAttribute('data-label'));

            cards.forEach(card => {
                const labels = card.querySelectorAll('.sd-card-footer img');
                let matchedLabels = [];

                labels.forEach(labelImg => {
                    const src = labelImg.src.split('/').pop().split('.')[0]; // Get the filename without extension

                    if (activeLabels.includes(src)) {
                        matchedLabels.push(src);
                    }
                });

                // Check if the card matches all active labels or if no labels are active
                if (activeLabels.length === 0 || (matchedLabels.length === activeLabels.length && matchedLabels.length > 0)) {
                    card.style.opacity = '1';
                } else {
                    card.style.opacity = '0.1';
                }
            });
        });
    });
});
