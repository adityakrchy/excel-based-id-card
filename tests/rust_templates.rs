use excel_id_card_rust::templates::{
    builtin_templates, load_builtin_template, TemplateError, BUILTIN_TEMPLATE_IDS,
};

#[test]
fn shipped_templates_are_available_to_the_native_crate() {
    let templates = builtin_templates().unwrap();
    assert_eq!(templates.len(), BUILTIN_TEMPLATE_IDS.len());
    assert!(templates
        .iter()
        .all(|template| !template.elements.is_empty()));
    assert_eq!(templates[0].id, "builtin-classic-portrait");
}

#[test]
fn unknown_builtin_template_is_a_typed_error() {
    assert!(matches!(
        load_builtin_template("does-not-exist"),
        Err(TemplateError::UnknownBuiltin(id)) if id == "does-not-exist"
    ));
}
