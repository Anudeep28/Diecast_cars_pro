// Dynamic dropdowns for manufacturer and seller
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dynamic dropdowns script loaded');
    
    // Initialize all input fields with data-dropdown-target attribute
    const dropdownInputs = document.querySelectorAll('input[data-dropdown-target]');
    console.log('Found dropdown inputs:', dropdownInputs.length);
    
    // Debug all input fields
    dropdownInputs.forEach(input => {
        console.log('Input field:', input.id);
        console.log('Data options attribute:', input.getAttribute('data-options'));
    });
    
    dropdownInputs.forEach(input => {
        const dropdownId = input.getAttribute('data-dropdown-target');
        console.log('Processing input with dropdown target:', dropdownId);
        
        const dropdownElement = document.getElementById(dropdownId);
        console.log('Found dropdown element:', dropdownElement ? 'Yes' : 'No');
        
        if (dropdownElement) {
            // Initialize the dropdown
            initializeDropdown(input, dropdownElement);
        } else {
            console.error('Dropdown element not found for ID:', dropdownId);
        }
    });
    
    function initializeDropdown(inputField, dropdownContainer) {
        console.log('Initializing dropdown for', inputField.id);
        
        // Get options from the data-options attribute
        let optionsData = inputField.getAttribute('data-options');
        let options = [];
        
        // Parse options data if it exists
        if (optionsData) {
            try {
                options = JSON.parse(optionsData);
                console.log('Parsed options for', inputField.id, ':', options);
            } catch (e) {
                console.error('Error parsing options for', inputField.id, ':', e);
                console.error('Raw options string:', optionsData);
            }
        }
        
        // Add event listeners
        inputField.addEventListener('focus', function() {
            console.log('Input focused');
            populateDropdown(dropdownContainer, this.value, options);
            dropdownContainer.classList.remove('d-none');
        });
        
        inputField.addEventListener('blur', function() {
            // Delay hiding to allow for click on dropdown items
            setTimeout(() => {
                dropdownContainer.classList.add('d-none');
            }, 200);
        });
        
        inputField.addEventListener('input', function() {
            populateDropdown(dropdownContainer, this.value, options);
        });
        
        // Add click event for the plus button
        const plusButton = inputField.closest('.input-group').querySelector('.input-group-text');
        if (plusButton) {
            console.log('Found plus button for', inputField.id);
            plusButton.addEventListener('click', function() {
                // Focus the input field if it's not already focused
                if (document.activeElement !== inputField) {
                    inputField.focus();
                }
            });
        } else {
            console.error('Plus button not found for', inputField.id);
        }
        
        // Initial population of dropdown
        populateDropdown(dropdownContainer, inputField.value, options);
    }
    
    function populateDropdown(container, searchText, options) {
        container.innerHTML = '';
        
        // Get the input field associated with this dropdown
        const inputField = document.querySelector(`input[data-dropdown-target="${container.id}"]`);
        if (!inputField) {
            console.error('Input field not found for dropdown', container.id);
            return;
        }
        
        // If options wasn't passed as a parameter, get them from the input field
        if (!options) {
            // Get options from the data-options attribute
            let optionsData = inputField.getAttribute('data-options');
            
            // If options is a string (JSON), parse it
            if (typeof optionsData === 'string') {
                try {
                    // Handle empty strings or undefined
                    if (!optionsData || optionsData === 'undefined' || optionsData === 'null') {
                        console.log('Empty options string, defaulting to empty array');
                        options = [];
                    } else {
                        options = JSON.parse(optionsData);
                        console.log('Parsed options for', container.id, ':', options);
                    }
                } catch (e) {
                    console.error('Error parsing options:', e);
                    console.error('Raw options string:', optionsData);
                    options = [];
                }
            }
        }
        
        // Ensure options is an array
        if (!Array.isArray(options)) {
            console.error('Options is not an array:', options);
            options = [];
        }
        
        const lowerSearchText = searchText.toLowerCase();
        let matchFound = false;
        
        // Filter options that match the search text
        const filteredOptions = options.filter(option => 
            option && option.toLowerCase().includes(lowerSearchText)
        );
        
        console.log('Filtered options:', filteredOptions);
        
        // Add matching options to dropdown
        filteredOptions.forEach(option => {
            const item = document.createElement('div');
            item.className = 'dropdown-item p-2 cursor-pointer';
            item.style.cursor = 'pointer';
            item.textContent = option;
            
            // Add hover effect
            item.addEventListener('mouseover', function() {
                this.classList.add('bg-light');
            });
            
            item.addEventListener('mouseout', function() {
                this.classList.remove('bg-light');
            });
            
            item.addEventListener('mousedown', function() {
                // Find the associated input field
                const inputField = document.querySelector(`input[data-dropdown-target="${container.id}"]`);
                if (inputField) {
                    inputField.value = option;
                    // Hide dropdown after selection
                    container.classList.add('d-none');
                }
            });
            
            container.appendChild(item);
            matchFound = true;
        });
        
        // Add separator if we have options and will add the "Add new" option
        if (matchFound && searchText.trim() !== '') {
            const separator = document.createElement('hr');
            separator.className = 'dropdown-divider my-1';
            container.appendChild(separator);
        }
        
        // Add "Add new" option if there's text
        if (searchText.trim() !== '') {
            const addNewItem = document.createElement('div');
            addNewItem.className = 'dropdown-item p-2 text-primary';
            addNewItem.style.cursor = 'pointer';
            
            // Get field name from input id to customize the message
            const inputField = document.querySelector(`input[data-dropdown-target="${container.id}"]`);
            const fieldName = inputField ? inputField.id.replace('id_', '') : '';
            const capitalizedFieldName = fieldName.charAt(0).toUpperCase() + fieldName.slice(1).replace('_', ' ');
            
            addNewItem.innerHTML = `<i class="fas fa-plus"></i> Add New ${capitalizedFieldName}: "${searchText}"`;
            
            // Add hover effect
            addNewItem.addEventListener('mouseover', function() {
                this.classList.add('bg-light');
            });
            
            addNewItem.addEventListener('mouseout', function() {
                this.classList.remove('bg-light');
            });
            
            addNewItem.addEventListener('mousedown', function() {
                if (inputField) {
                    inputField.value = searchText;
                    // Hide dropdown after selection
                    container.classList.add('d-none');
                }
            });
            
            container.appendChild(addNewItem);
        }
        
        // If no options and no search text, show a message
        if (container.children.length === 0) {
            const noOptions = document.createElement('div');
            noOptions.className = 'dropdown-item p-2 text-muted';
            noOptions.textContent = 'No options available';
            container.appendChild(noOptions);
        }
    }
});
