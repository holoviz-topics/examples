document.addEventListener('DOMContentLoaded', function () {
    const buttons = document.querySelectorAll('.filter-btn');
    const cols = document.querySelectorAll('.sd-col');

    // console.log('Filter buttons:', buttons);
    // console.log('Grid columns (cards):', cols);

    buttons.forEach(button => {
        button.addEventListener('click', function () {
            // Toggle the custom active class on the clicked button
            this.classList.toggle('filter-btn-active');
            // console.log('Button clicked:', this);
            // console.log('Active state:', this.classList.contains('filter-btn-active'));

            // Determine active labels
            let activeLabels = Array.from(buttons)
                                    .filter(btn => btn.classList.contains('filter-btn-active'))
                                    .map(btn => btn.getAttribute('data-label'));

            // console.log('Active labels:', activeLabels);

            cols.forEach(col => {
                const labels = col.querySelectorAll('.sd-card-footer img');
                let matchedLabels = [];

                labels.forEach(labelImg => {
                    const src = labelImg.src.split('/').pop().split('.')[0]; // Get the filename without extension
                    // console.log('Label src:', src);

                    if (activeLabels.includes(src)) {
                        matchedLabels.push(src);
                    }
                });

                // console.log('Matched labels:', matchedLabels);

                // Check if the col matches all active labels or if no labels are active
                if (activeLabels.length === 0 || (matchedLabels.length === activeLabels.length && matchedLabels.length > 0)) {
                    col.style.display = 'block';
                    // console.log('Showing column:', col);
                } else {
                    col.style.display = 'none';
                    // console.log('Hiding column:', col);
                }
            });
        });
    });
});