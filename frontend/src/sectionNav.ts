export const goToSection = (id: string) => {
    document.getElementById('section-' + id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};
