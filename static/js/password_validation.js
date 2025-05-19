function PasswordMatchValidator(el, password, password2) {
    el.classList.remove("text-muted");
    if (password.value.length <= 2) {
      el.classList.remove("valid","text-dark");
      el.classList.add("invalid","text-muted");
    } else {
      if (password2.value != password.value) {
          el.classList.remove("valid","text-dark");
          el.classList.add("invalid","text-muted");
      } else {
          el.classList.remove("invalid","text-muted");
          el.classList.add("valid","text-dark");
      }
    }
}

function AllPasswordValidators(data, password) {
  data.forEach((element) => {
    var el = document.querySelector("."+element["validator_name"])
    el.classList.remove("text-muted");
    if (password.value.length <= 2) {
        el.classList.remove("valid","text-dark");
        el.classList.add("invalid","text-muted");
    } else {
        if (element["isValid"]) {
            el.classList.remove("invalid","text-muted");
            el.classList.add("valid","text-dark");
        } else {
            el.classList.remove("valid","text-dark");
            el.classList.add("invalid","text-muted");
        }
    }
  });
}

function PasswordAlertState(data, password, password2, password_requirements) {
  const isTrue = (currentValue) => currentValue["isValid"] === true;
  if (data.every(isTrue)) {
    if (password2.value != password.value) {
      password_requirements.classList.remove("alert-password-success");
      password_requirements.classList.add("alert-password");
    } else {
      password_requirements.classList.remove("alert-password");
      password_requirements.classList.add("alert-password-success");
    }
  } else {
    password_requirements.classList.remove("alert-password-success");
    password_requirements.classList.add("alert-password");
  }
}

function PasswordEvents(password_element_name, password2_element_name, data, url) {
    const password_requirements = document.getElementById("password_requirements");
    const requirements = document.querySelectorAll(".requirements");
    const password = document.getElementById(password_element_name);
    const password2 = document.getElementById(password2_element_name);
    requirements.forEach((element) => element.classList.add("invalid"));
    password.addEventListener("input", () => {
        data.password = password.value;
        $.ajax({
            url: url,
            data: JSON.stringify(data),
            type: "POST",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            success: (data) => {
              var el = document.querySelector(".PasswordMatch")
              PasswordMatchValidator(el, password, password2);
              AllPasswordValidators(data, password);
              PasswordAlertState(data, password, password2, password_requirements);
            },
            error: (error) => {
              console.log(error);
            }
          });
    });

    password2.addEventListener("input", () => {
        data.password = password.value;
        $.ajax({
          url: url,
          data: JSON.stringify(data),
          type: "POST",
          contentType: "application/json; charset=utf-8",
          dataType: "json",
          success: (data) => {
            var el = document.querySelector(".PasswordMatch")
            PasswordMatchValidator(el, password, password2);
            PasswordAlertState(data, password, password2, password_requirements);
          },
          error: (error) => {
            console.log(error);
          }
        });
    });

}
