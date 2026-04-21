const addUserModalEl = document.getElementById("addUserModal");
let addUserModal = null;
const defaultOneTimePassword = "Tra@2026";

document.addEventListener("DOMContentLoaded", () => {
  if (addUserModalEl) {
    addUserModal = new bootstrap.Modal(addUserModalEl);
  }

  toggleFields();

  document.querySelectorAll(".password-toggle").forEach((toggleBtn) => {
    toggleBtn.addEventListener("click", () => {
      const input = document.getElementById(toggleBtn.dataset.target);
      const icon = toggleBtn.querySelector("i");
      if (!input || !icon) return;

      const showPassword = input.type === "password";
      input.type = showPassword ? "text" : "password";
      icon.className = showPassword ? "bi bi-eye-slash" : "bi bi-eye";
      toggleBtn.setAttribute(
        "aria-label",
        showPassword ? "Hide password" : "Show password",
      );
    });
  });
});

function openAddUserModal() {
  if (addUserModal) addUserModal.show();
  // Reset form when opening modal
  const form = document.querySelector("#addUserModal form");
  if (form) {
    form.reset();
    // Reset user type to student
    document.getElementById("userTypeSelect").value = "student";
    document.getElementById("userTypeHidden").value = "student";
    const passwordInput = document.getElementById("addUserPassword");
    if (passwordInput) {
      passwordInput.value = defaultOneTimePassword;
    }
    toggleFields();
    // Clear any error styling
    clearAllAddUserErrors();
    // Remove dynamically created error divs for board/grade
    const boardError = document.getElementById("boardError");
    if (boardError && boardError.parentNode) {
      boardError.parentNode.removeChild(boardError);
    }
    const gradeError = document.getElementById("gradeError");
    if (gradeError && gradeError.parentNode) {
      gradeError.parentNode.removeChild(gradeError);
    }
    // Remove is-invalid class from board/grade selects
    const boardSelect = form.querySelector('[name="board"]');
    const gradeSelect = form.querySelector('[name="grade"]');
    if (boardSelect) boardSelect.classList.remove("is-invalid");
    if (gradeSelect) gradeSelect.classList.remove("is-invalid");
  }
}

function toggleFields() {
  const type = document.getElementById("userTypeSelect").value;

  document.getElementById("userTypeHidden").value = type;

  const studentFields = document.getElementById("studentFields");
  const teacherFields = document.getElementById("teacherFields");
  const studentInputs = studentFields.querySelectorAll("input, select, textarea");
  const teacherInputs = teacherFields.querySelectorAll("input, select, textarea");

  if (type === "student") {
    studentFields.style.display = "flex";
    teacherFields.style.display = "none";
    studentInputs.forEach((input) => {
      input.disabled = false;
    });
    teacherInputs.forEach((input) => {
      input.disabled = true;
    });
  } else {
    studentFields.style.display = "none";
    teacherFields.style.display = "flex";
    studentInputs.forEach((input) => {
      input.disabled = true;
    });
    teacherInputs.forEach((input) => {
      input.disabled = false;
    });
  }
}

function showFieldError(inputId, message) {
  const input = document.getElementById(inputId);
  if (input) {
    input.classList.add("is-invalid");
    const errorDiv = document.getElementById(inputId + "Error");
    if (errorDiv) {
      errorDiv.textContent = message;
    }
  }
}

function clearFieldError(inputId) {
  const input = document.getElementById(inputId);
  if (input) {
    input.classList.remove("is-invalid");
    const errorDiv = document.getElementById(inputId + "Error");
    if (errorDiv) {
      errorDiv.textContent = "";
    }
  }
}

function clearAllAddUserErrors() {
  const fields = ["name", "username", "email", "contact"];
  fields.forEach((fieldId) => {
    const input = document.querySelector(`#addUserModal [name="${fieldId}"]`);
    if (input) {
      input.classList.remove("is-invalid");
    }
    const errorDiv = document.getElementById(fieldId + "Error");
    if (errorDiv) {
      errorDiv.textContent = "";
    }
  });
}

function validateAndSubmitAddUser() {
  const form = document.querySelector("#addUserModal form");
  const nameInput = form.querySelector('[name="name"]');
  const usernameInput = form.querySelector('[name="username"]');
  const emailInput = form.querySelector('[name="email"]');
  const contactInput = form.querySelector('[name="contact"]');

  // Get the user type to determine which fields to validate
  const userType = document.getElementById("userTypeSelect").value;

  // Clear previous errors
  clearAllAddUserErrors();

  let isValid = true;

  // Validate name - only alphabets and spaces
  const nameValue = nameInput.value.trim();
  const nameRegex = /^[a-zA-Z\s]+$/;
  if (!nameValue) {
    nameInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("nameError");
    if (errorDiv) errorDiv.textContent = "Name is required";
    isValid = false;
  } else if (!nameRegex.test(nameValue)) {
    nameInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("nameError");
    if (errorDiv) errorDiv.textContent = "Name should contain only letters and spaces";
    isValid = false;
  }

  // Validate username
  const usernameValue = usernameInput.value.trim();
  if (!usernameValue) {
    usernameInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("usernameError");
    if (errorDiv) errorDiv.textContent = "Username is required";
    isValid = false;
  }

  // Validate email
  const emailValue = emailInput.value.trim();
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (!emailValue) {
    emailInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("emailError");
    if (errorDiv) errorDiv.textContent = "Email is required";
    isValid = false;
  } else if (!emailRegex.test(emailValue)) {
    emailInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("emailError");
    if (errorDiv) errorDiv.textContent = "Please enter a valid email address";
    isValid = false;
  }

  // Validate contact - only 10 digits
  const contactValue = contactInput.value.trim();
  const contactRegex = /^\d{10}$/;
  if (!contactValue) {
    contactInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("contactError");
    if (errorDiv) errorDiv.textContent = "Contact number is required";
    isValid = false;
  } else if (!contactRegex.test(contactValue)) {
    contactInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("contactError");
    if (errorDiv) errorDiv.textContent = "Contact must be exactly 10 digits";
    isValid = false;
  }

  // For students, validate board and grade
  if (userType === "student") {
    const boardSelect = form.querySelector('[name="board"]');
    const gradeSelect = form.querySelector('[name="grade"]');
    const boardErrorId = "boardError";
    const gradeErrorId = "gradeError";

    // Create error divs if they don't exist
    if (boardSelect && !document.getElementById(boardErrorId)) {
      const errorDiv = document.createElement("div");
      errorDiv.id = boardErrorId;
      errorDiv.className = "invalid-feedback";
      errorDiv.style.display = "block";
      boardSelect.parentNode.appendChild(errorDiv);
    }
    if (gradeSelect && !document.getElementById(gradeErrorId)) {
      const errorDiv = document.createElement("div");
      errorDiv.id = gradeErrorId;
      errorDiv.className = "invalid-feedback";
      errorDiv.style.display = "block";
      gradeSelect.parentNode.appendChild(errorDiv);
    }

    if (boardSelect && !boardSelect.value) {
      boardSelect.classList.add("is-invalid");
      const errorDiv = document.getElementById(boardErrorId);
      if (errorDiv) errorDiv.textContent = "Board is required";
      isValid = false;
    } else if (boardSelect) {
      boardSelect.classList.remove("is-invalid");
      const errorDiv = document.getElementById(boardErrorId);
      if (errorDiv) errorDiv.textContent = "";
    }

    if (gradeSelect && !gradeSelect.value) {
      gradeSelect.classList.add("is-invalid");
      const errorDiv = document.getElementById(gradeErrorId);
      if (errorDiv) errorDiv.textContent = "Grade is required";
      isValid = false;
    } else if (gradeSelect) {
      gradeSelect.classList.remove("is-invalid");
      const errorDiv = document.getElementById(gradeErrorId);
      if (errorDiv) errorDiv.textContent = "";
    }
  }

  if (!isValid) {
    return;
  }

  // All validations passed, submit the form
  // Hide modal before submitting to prevent any timing issues
  if (addUserModal) {
    addUserModal.hide();
  }

  // All validations passed, submit the form
  form.submit();
}

// Add direct input filtering for contact field to prevent alphabets
document.addEventListener("DOMContentLoaded", function () {
  const contactInputs = document.querySelectorAll(".number-only");
  contactInputs.forEach((input) => {
    input.addEventListener("input", function () {
      // Remove any non-digit characters
      this.value = this.value.replace(/\D/g, "");
      // Limit to 10 digits
      if (this.value.length > 10) {
        this.value = this.value.slice(0, 10);
      }
    });

    // Also handle paste event
    input.addEventListener("paste", function (e) {
      e.preventDefault();
      const pastedText = (e.clipboardData || window.clipboardData).getData(
        "text",
      );
      const filtered = pastedText.replace(/\D/g, "").slice(0, 10);
      this.value = filtered;
    });
  });
});

document.addEventListener("input", (e) => {
  if (e.target.classList.contains("alpha-only")) {
    e.target.value = e.target.value.replace(/[^a-zA-Z\s]/g, "");
  }

  if (e.target.classList.contains("number-only")) {
    e.target.value = e.target.value.replace(/\D/g, "");
  }
});

function confirmDelete(message = "Are you sure you want to delete this user?") {
  return confirm(message);
}

const editStudentModal = document.getElementById("editStudentModal");

if (editStudentModal) {
  editStudentModal.addEventListener("show.bs.modal", function (event) {
    const button = event.relatedTarget;

    const id = button.dataset.id;

    const form = document.getElementById("editStudentForm");
    form.action = `/edit-student/${id}/`;

    document.getElementById("editStudentName").value =
      button.dataset.name || "";
    document.getElementById("editStudentEmail").value =
      button.dataset.email || "";

    document.getElementById("editStudentContact").value =
      button.dataset.contact || "";

    document.getElementById("editStudentSchool").value =
      button.dataset.school || "";

    document.getElementById("editStudentBoard").value =
      button.dataset.board || "";

    document.getElementById("editStudentGrade").value =
      button.dataset.grade || "";

    document.getElementById("editStudentGender").value =
      button.dataset.gender || "";

    document.getElementById("editStudentBatch").value =
      button.dataset.batch || "";
  });
}

const editTeacherModal = document.getElementById("editTeacherModal");

if (editTeacherModal) {
  editTeacherModal.addEventListener("show.bs.modal", function (event) {
    const button = event.relatedTarget;

    const id = button.dataset.id;

    const form = document.getElementById("editTeacherForm");
    form.action = `/edit-teacher/${id}/`;

    document.getElementById("editTeacherName").value =
      button.dataset.name || "";

    document.getElementById("editTeacherUsername").value =
      button.dataset.username || "";

    document.getElementById("editTeacherEmail").value =
      button.dataset.email || "";

    document.getElementById("editTeacherContact").value =
      button.dataset.contact || "";

    document.getElementById("editTeacherGender").value =
      button.dataset.gender || "";

    document.getElementById("editTeacherRole").value =
      button.dataset.role || "";

    document.getElementById("editTeacherSubjects").value =
      button.dataset.subjects || "";

    document.getElementById("editTeacherGrade").value =
      button.dataset.grade || "";

    document.getElementById("editTeacherBoard").value =
      button.dataset.board || "";

    document.getElementById("editTeacherBatch").value =
      button.dataset.batch || "";
  });
}
