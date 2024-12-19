document.addEventListener('DOMContentLoaded', function () {
    const buttons = document.querySelectorAll('.filter-btn');
    const sortOptions = document.getElementById('sort-options');
    const allContainers = document.querySelectorAll('.sd-row');

    function filterCards() {
        let activeLabels = Array.from(buttons)
            .filter(btn => btn.classList.contains('filter-btn-active'))
            .map(btn => btn.getAttribute('data-label'));

        allContainers.forEach(cardsContainer => {
            const cards = Array.from(cardsContainer.getElementsByClassName('sd-col'));
            cards.forEach(card => {
                const labels = card.querySelectorAll('span.sd-badge');
                let matchedLabels = [];

                labels.forEach(labelBdg => {
                    const src = labelBdg.textContent
                    if (activeLabels.includes(src)) {
                        matchedLabels.push(src);
                    }
                });

                // Check if the card matches all active labels or if no labels are active
                if (activeLabels.length === 0 || (matchedLabels.length === activeLabels.length && matchedLabels.length > 0)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }

    function sortCards(criteria) {
        allContainers.forEach(cardsContainer => {
            const cards = Array.from(cardsContainer.getElementsByClassName('sd-col'));

            cards.sort((a, b) => {
                if (criteria === 'title') {
                    const titleA = a.querySelector('.sd-card-title a').textContent.trim();
                    const titleB = b.querySelector('.sd-card-title a').textContent.trim();
                    return titleA.localeCompare(titleB);
                } else if (criteria === 'date') {
                    const dateStrA = a.querySelector('.last-updated').textContent.trim().split(': ')[1];
                    const dateStrB = b.querySelector('.last-updated').textContent.trim().split(': ')[1];
                    const dateA = new Date(dateStrA);
                    const dateB = new Date(dateStrB);
                    return dateB - dateA; // Most recent first
                }
            });

            // Remove all cards from the container and append sorted cards
            cards.forEach(card => cardsContainer.appendChild(card));
        });
    }

    // Event listeners for filter buttons
    buttons.forEach(button => {
        button.addEventListener('click', function () {
            // Toggle the custom active class on the clicked button
            this.classList.toggle('filter-btn-active');
            filterCards();
        });
    });

    // Event listener for the sort dropdown
    sortOptions.addEventListener('change', function () {
        const criteria = sortOptions.value;
        sortCards(criteria);
    });
});
