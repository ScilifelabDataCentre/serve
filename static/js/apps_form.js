$(document).ready(function() {
  function toggleLinkNoteVisibility() {
    if ($('#permission').val() == 'link') {
      $('#id_link_only_note').show();
      $('#link_privacy_type_note').attr('required', true);
      $('#link_privacy_type_note').addClass('validate-item');
      $('#link_privacy_type_note').attr('type', 'text'); // Make it visible
    } else {
      $('#id_link_only_note').hide();
      $('#link_privacy_type_note').removeAttr('required');
      $('#link_privacy_type_note').removeClass('validate-item');
      $('#link_privacy_type_note').attr('type', 'hidden'); // Hide it
    }
  }

  // Initial check on document ready
  toggleLinkNoteVisibility();

  // Setup change event handler
  $('#permission').change(toggleLinkNoteVisibility);
});
