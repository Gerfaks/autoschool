const todoState = {
    categories: [],
    items: [],
};

const priorityLabels = {
    high: 'Высокий',
    normal: 'Обычный',
    low: 'Низкий',
};

async function todoRequest(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || 'Не удалось выполнить действие');
    }
    return data;
}

function getCategoryById(id) {
    return todoState.categories.find((category) => String(category.id) === String(id));
}

function fillCategorySelects() {
    const taskSelect = document.getElementById('todo-category');
    const filterSelect = document.getElementById('filter-category');
    taskSelect.innerHTML = '<option value="">Без категории</option>';
    filterSelect.innerHTML = '<option value="">Все категории</option>';

    todoState.categories.forEach((category) => {
        taskSelect.insertAdjacentHTML('beforeend', `<option value="${category.id}">${category.name}</option>`);
        filterSelect.insertAdjacentHTML('beforeend', `<option value="${category.id}">${category.name}</option>`);
    });
}

function renderCategories() {
    const list = document.getElementById('category-list');
    list.innerHTML = '';
    if (!todoState.categories.length) {
        list.innerHTML = '<div class="text-muted">Категории пока не добавлены</div>';
        return;
    }

    todoState.categories.forEach((category) => {
        const row = document.createElement('div');
        row.className = 'category-row';
        row.innerHTML = `
            <div class="category-name">
                <span class="category-dot" style="background:${category.color}"></span>
                <span>${escapeHtml(category.name)}</span>
            </div>
            <div class="d-flex gap-1">
                <button type="button" class="btn btn-sm btn-warning" data-edit-category="${category.id}">
                    <i class="fas fa-pen"></i>
                </button>
                <button type="button" class="btn btn-sm btn-danger" data-delete-category="${category.id}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        list.appendChild(row);
    });
}

function updateCounters(counts) {
    document.getElementById('count-total').textContent = counts.total || 0;
    document.getElementById('count-active').textContent = counts.active || 0;
    document.getElementById('count-completed').textContent = counts.completed || 0;
    document.getElementById('count-overdue').textContent = counts.overdue || 0;
}

function renderItems() {
    const list = document.getElementById('todo-list');
    const empty = document.getElementById('todo-empty');
    list.innerHTML = '';
    empty.classList.toggle('d-none', todoState.items.length > 0);

    todoState.items.forEach((item) => {
        const category = item.category;
        const categoryChip = category
            ? `<span class="todo-chip"><span class="category-dot" style="background:${category.color}"></span>${escapeHtml(category.name)}</span>`
            : '<span class="todo-chip"><i class="fas fa-tag"></i> Без категории</span>';
        const dueClass = item.isComplete ? 'done' : item.isOverdue ? 'overdue' : '';
        const dueIcon = item.isComplete ? 'fa-check' : item.isOverdue ? 'fa-triangle-exclamation' : 'fa-calendar-day';

        const row = document.createElement('article');
        row.className = `todo-item ${item.isComplete ? 'complete' : ''}`;
        row.innerHTML = `
            <input type="checkbox" class="todo-check" data-toggle-item="${item.id}" ${item.isComplete ? 'checked' : ''}>
            <div>
                <div class="todo-title">${escapeHtml(item.title)}</div>
                ${item.description ? `<div class="todo-description">${escapeHtml(item.description)}</div>` : ''}
                <div class="todo-meta">
                    ${categoryChip}
                    <span class="todo-chip ${dueClass}"><i class="fas ${dueIcon}"></i> ${item.dueDateLabel}</span>
                    <span class="todo-chip priority-${item.priority}"><i class="fas fa-flag"></i> ${priorityLabels[item.priority]}</span>
                </div>
            </div>
            <div class="todo-actions">
                <button type="button" class="btn btn-sm btn-warning" data-edit-item="${item.id}">
                    <i class="fas fa-pen"></i>
                </button>
                <button type="button" class="btn btn-sm btn-danger" data-delete-item="${item.id}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        list.appendChild(row);
    });
}

function getFilterQuery() {
    const params = new URLSearchParams();
    const q = document.getElementById('filter-query').value.trim();
    const status = document.getElementById('filter-status').value;
    const categoryId = document.getElementById('filter-category').value;
    const priority = document.getElementById('filter-priority').value;
    if (q) params.set('q', q);
    if (status) params.set('status', status);
    if (categoryId) params.set('category_id', categoryId);
    if (priority) params.set('priority', priority);
    return params.toString();
}

async function loadCategories() {
    todoState.categories = await todoRequest('/api/todo/categories');
    fillCategorySelects();
    renderCategories();
}

async function loadItems() {
    const query = getFilterQuery();
    const data = await todoRequest(`/api/todo/items${query ? '?' + query : ''}`);
    todoState.items = data.items || [];
    updateCounters(data.counts || {});
    renderItems();
}

function resetTodoForm() {
    document.getElementById('todo-form').reset();
    document.getElementById('todo-id').value = '';
    document.getElementById('todo-submit').innerHTML = '<i class="fas fa-plus"></i> Добавить';
    document.getElementById('todo-cancel').classList.add('d-none');
}

function resetCategoryForm() {
    document.getElementById('category-form').reset();
    document.getElementById('category-id').value = '';
    document.getElementById('category-color').value = '#b84d3f';
    document.getElementById('category-submit').innerHTML = '<i class="fas fa-plus"></i> Добавить';
    document.getElementById('category-cancel').classList.add('d-none');
}

function fillTodoForm(item) {
    document.getElementById('todo-id').value = item.id;
    document.getElementById('todo-title').value = item.title;
    document.getElementById('todo-description').value = item.description || '';
    document.getElementById('todo-category').value = item.categoryId || '';
    document.getElementById('todo-due-date').value = item.dueDate || '';
    document.getElementById('todo-priority').value = item.priority || 'normal';
    document.getElementById('todo-complete').checked = item.isComplete;
    document.getElementById('todo-submit').innerHTML = '<i class="fas fa-save"></i> Сохранить';
    document.getElementById('todo-cancel').classList.remove('d-none');
}

function getTodoFormData() {
    return {
        title: document.getElementById('todo-title').value,
        description: document.getElementById('todo-description').value,
        categoryId: document.getElementById('todo-category').value || null,
        dueDate: document.getElementById('todo-due-date').value,
        priority: document.getElementById('todo-priority').value,
        isComplete: document.getElementById('todo-complete').checked,
    };
}

function fillCategoryForm(category) {
    document.getElementById('category-id').value = category.id;
    document.getElementById('category-name').value = category.name;
    document.getElementById('category-color').value = category.color || '#b84d3f';
    document.getElementById('category-submit').innerHTML = '<i class="fas fa-save"></i> Сохранить';
    document.getElementById('category-cancel').classList.remove('d-none');
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

document.getElementById('todo-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = document.getElementById('todo-id').value;
    const payload = getTodoFormData();
    try {
        if (id) {
            await todoRequest(`/api/todo/items/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
        } else {
            await todoRequest('/api/todo/items', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
        }
        resetTodoForm();
        await loadItems();
    } catch (error) {
        alert(error.message);
    }
});

document.getElementById('category-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const id = document.getElementById('category-id').value;
    const payload = {
        name: document.getElementById('category-name').value,
        color: document.getElementById('category-color').value,
    };
    try {
        if (id) {
            await todoRequest(`/api/todo/categories/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
        } else {
            await todoRequest('/api/todo/categories', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
        }
        resetCategoryForm();
        await loadCategories();
        await loadItems();
    } catch (error) {
        alert(error.message);
    }
});

document.getElementById('todo-cancel').addEventListener('click', resetTodoForm);
document.getElementById('category-cancel').addEventListener('click', resetCategoryForm);

document.getElementById('todo-filters').addEventListener('input', loadItems);
document.getElementById('todo-filters').addEventListener('change', loadItems);

document.addEventListener('click', async (event) => {
    const editItemId = event.target.closest('[data-edit-item]')?.dataset.editItem;
    const deleteItemId = event.target.closest('[data-delete-item]')?.dataset.deleteItem;
    const editCategoryId = event.target.closest('[data-edit-category]')?.dataset.editCategory;
    const deleteCategoryId = event.target.closest('[data-delete-category]')?.dataset.deleteCategory;

    if (editItemId) {
        const item = todoState.items.find((candidate) => String(candidate.id) === String(editItemId));
        if (item) fillTodoForm(item);
    }

    if (deleteItemId && confirm('Удалить дело?')) {
        await todoRequest(`/api/todo/items/${deleteItemId}`, {method: 'DELETE'});
        await loadItems();
    }

    if (editCategoryId) {
        const category = getCategoryById(editCategoryId);
        if (category) fillCategoryForm(category);
    }

    if (deleteCategoryId && confirm('Удалить категорию? Дела останутся без категории.')) {
        await todoRequest(`/api/todo/categories/${deleteCategoryId}`, {method: 'DELETE'});
        await loadCategories();
        await loadItems();
    }
});

document.addEventListener('change', async (event) => {
    const toggleId = event.target.dataset.toggleItem;
    if (!toggleId) return;
    const item = todoState.items.find((candidate) => String(candidate.id) === String(toggleId));
    if (!item) return;
    await todoRequest(`/api/todo/items/${toggleId}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            title: item.title,
            description: item.description,
            categoryId: item.categoryId,
            dueDate: item.dueDate,
            priority: item.priority,
            isComplete: event.target.checked,
        }),
    });
    await loadItems();
});

Promise.all([loadCategories()]).then(loadItems);
