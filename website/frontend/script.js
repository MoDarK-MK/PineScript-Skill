// Micro-animations for scroll reveals
document.addEventListener('DOMContentLoaded', () => {
    const reveals = document.querySelectorAll('.reveal');

    const revealOnScroll = () => {
        const windowHeight = window.innerHeight;
        const elementVisible = 100;

        reveals.forEach((reveal) => {
            const elementTop = reveal.getBoundingClientRect().top;
            if (elementTop < windowHeight - elementVisible) {
                reveal.classList.add('active');
            }
        });
    };

    // Initial check and scroll listener
    revealOnScroll();
    window.addEventListener('scroll', revealOnScroll);
});

// Copy to clipboard functionality
function copyCommand() {
    const cmdText = document.querySelector('.cmd-text').innerText;
    const copyBtn = document.querySelector('.copy-btn');
    const icon = copyBtn.querySelector('i');

    navigator.clipboard.writeText(cmdText).then(() => {
        // Change icon to checkmark
        icon.classList.remove('ph-copy');
        icon.classList.add('ph-check', 'text-accent');
        
        // Revert back after 2 seconds
        setTimeout(() => {
            icon.classList.remove('ph-check', 'text-accent');
            icon.classList.add('ph-copy');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy text: ', err);
    });
}
