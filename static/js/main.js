document.addEventListener('DOMContentLoaded', function () {
    const deleteButtons = document.querySelectorAll('form[action*="delete_book"]');
    deleteButtons.forEach(form => {
        form.addEventListener('submit', function (event) {
            if (!confirm('Are you sure you want to delete this book?')) {
                event.preventDefault();
            }
        });
    });
});
