document.addEventListener("DOMContentLoaded", function() {
    if (document.getElementById("description")) {
        let easyMDE = new EasyMDE({ element: document.getElementById("description") });
    }
});