$(document).ready(function() {
  const $permission = $('#permission');
  const $idLinkOnlyNote = $('#id_link_only_note');
  const $linkPrivacyTypeNote = $('#link_privacy_type_note');
  const $sourceCodeUrl = $('#source_code_url');

  function updatePermissionReqs() {
    // Toggle link note visibility and attributes
    if ($permission.val() === 'link') {
      $idLinkOnlyNote.show();
      $linkPrivacyTypeNote.attr({'required': true, 'type': 'text'}).addClass('validate-item');
    } else {
      $idLinkOnlyNote.hide();
      $linkPrivacyTypeNote.removeAttr('required').removeClass('validate-item').attr('type', 'hidden');
    }

    // Change source URL required attribute
    $sourceCodeUrl.attr('required', $permission.val() === 'public');
  }

  // Initial check on document ready
  updatePermissionReqs();

  // On every change for 'permission' dropdown
  $permission.change(updatePermissionReqs);
});
