// Tag Complete only watches its own textareas. The brief is a normal box, so attach it once.
onAfterUiUpdate(() => {
    const area = gradioApp().querySelector("#mossy_brief textarea");
    if (!area || area.classList.contains("autocomplete")) return;
    if (typeof addAutocompleteToArea !== "function" || !TAC_CFG?.activeIn?.thirdParty) return;
    addAutocompleteToArea(area);
});
