(() => {
  const grade = document.getElementById('class-grade');
  const division = document.getElementById('class-division');
  const student = document.getElementById('student-id');
  const count = document.getElementById('student-count');
  const hint = document.getElementById('add-student-hint');
  const addStudentLink = hint.querySelector('a');
  const save = document.getElementById('save-loan');
  const options = Array.from(student.querySelectorAll('option[data-grade]'));
  function updateStudents() {
    const ready = Boolean(grade.value && division.value);
    student.disabled = !ready;
    student.value = '';
    let visible = 0;
    options.forEach(option => {
      const match = ready && option.dataset.grade === grade.value && option.dataset.division === division.value;
      option.hidden = !match;
      option.disabled = !match;
      if (match) visible++;
    });
    student.querySelector('option[value=""]').textContent = ready ? (visible ? 'Select student by roll number' : 'No students in this class/division') : 'Select class and division first';
    count.textContent = !ready ? 'Choose a class to begin.' : visible + ' student' + (visible === 1 ? '' : 's') + ' found, sorted by roll number.';
    hint.hidden = !(ready && visible === 0);
    addStudentLink.href = '/students/new?grade=' + encodeURIComponent(grade.value || '6') + '&division=' + encodeURIComponent(division.value || 'A');
    save.disabled = true;
  }
  function updateDivisions() {
    division.value = '';
    student.value = '';
    division.disabled = !grade.value;
    division.querySelector('option[value=""]').textContent = grade.value ? 'Select division' : 'Select class first';
    Array.from(division.options).slice(1).forEach(option => { option.hidden = false; });
    updateStudents();
  }
  grade.addEventListener('change', updateDivisions);
  division.addEventListener('change', updateStudents);
  student.addEventListener('change', () => { save.disabled = !student.value; });
  document.getElementById('loan-form').addEventListener('submit', event => {
    if (!grade.value || !division.value || !student.value) {
      event.preventDefault();
      alert('Please choose the class, division and student before saving.');
    }
  });
  // Initialize controls on page load. Inline scripts were blocked by the app's CSP.
  updateDivisions();
})();