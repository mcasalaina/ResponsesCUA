'''
This is a UI version of the CUA (Computer Using Agent) app that displays the VNC output
and provides controls through a side panel.
'''

import argparse
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
import PIL
from PIL import Image, ImageTk
import base64
import io
import openai

import cua
from local_computer import LocalComputer
from vnc_computer import VNCComputer

class RedirectText:
    """Redirect print statements to the Text widget with rich text formatting"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""
        
        # Configure text tags for different actors
        self.text_widget.tag_configure("user", foreground="black", font=('Arial', 12, 'bold'))
        self.text_widget.tag_configure("agent", foreground="blue", font=('Arial', 12, 'bold'))
        self.text_widget.tag_configure("action", foreground="dark green", font=('Arial', 12, 'bold'))
        self.text_widget.tag_configure("normal", font=('Arial', 12))

    def write(self, string):
        self.buffer += string
        self.text_widget.config(state=tk.NORMAL)
        
        # Identify actor prefixes and apply appropriate tags
        if string.startswith("User: "):
            self.text_widget.insert(tk.END, "User: ", "user")
            self.text_widget.insert(tk.END, string[6:], "normal")
        elif string.startswith("Agent: "):
            self.text_widget.insert(tk.END, "Agent: ", "agent")
            self.text_widget.insert(tk.END, string[7:], "normal")
        elif string.startswith("Action: "):
            self.text_widget.insert(tk.END, "Action: ", "action")
            self.text_widget.insert(tk.END, string[8:], "normal")
        else:
            self.text_widget.insert(tk.END, string, "normal")
            
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)
    
    def flush(self):
        pass

class CUAApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CUA UI Application")
        self.root.geometry("1274x768")  # 1024 + 250 width
        self.root.minsize(1274, 768)

        # Set up logging
        logging.basicConfig(level=logging.WARNING, format='%(message)s')
        logging.getLogger("cua").setLevel(logging.DEBUG)
        
        # Variables
        self.running = False
        self.agent = None
        self.computer = None
        self.screenshot_image = None  # Original PIL Image
        self.screenshot_photo = None  # PhotoImage for display
        self.last_base64_img = None   # Store last screenshot data

        # Create frames
        self.create_frames()
        
        # Create sidebar controls
        self.create_sidebar_controls()
        
        # Create central area
        self.create_central_area()
        
        # Create log area
        self.create_log_area()
        
        # Bind resize event
        self.root.bind("<Configure>", self.on_resize)

    def create_frames(self):
        # Main layout as a PanedWindow to allow resizing with a slider
        self.main_frame = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left frame for VNC output
        self.vnc_frame = ttk.Frame(self.main_frame, width=1024, height=768)
        
        # Right frame for controls
        self.controls_frame = ttk.Frame(self.main_frame, width=250)
        
        # Add frames to the PanedWindow
        self.main_frame.add(self.vnc_frame, weight=4)  # VNC frame gets more space
        self.main_frame.add(self.controls_frame, weight=1)  # Controls get less space

    def create_sidebar_controls(self):
        # Parameters frame
        params_frame = ttk.LabelFrame(self.controls_frame, text="Parameters")
        params_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # VM Address
        ttk.Label(params_frame, text="VM Address:").pack(anchor=tk.W, padx=5, pady=2)
        self.vm_address_var = tk.StringVar(value="172.21.23.116")
        ttk.Entry(params_frame, textvariable=self.vm_address_var, font=('Arial', 12)).pack(fill=tk.X, padx=5, pady=2)
        
        # Environment
        ttk.Label(params_frame, text="Environment:").pack(anchor=tk.W, padx=5, pady=2)
        self.environment_var = tk.StringVar(value="linux")
        ttk.Entry(params_frame, textvariable=self.environment_var, font=('Arial', 12)).pack(fill=tk.X, padx=5, pady=2)
        
        # Model
        ttk.Label(params_frame, text="Model:").pack(anchor=tk.W, padx=5, pady=2)
        self.model_var = tk.StringVar(value="computer-use-preview")
        ttk.Entry(params_frame, textvariable=self.model_var, font=('Arial', 12)).pack(fill=tk.X, padx=5, pady=2)
        
        # Endpoint
        ttk.Label(params_frame, text="Endpoint:").pack(anchor=tk.W, padx=5, pady=2)
        self.endpoint_var = tk.StringVar(value="azure")
        endpoint_frame = ttk.Frame(params_frame)
        endpoint_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Radiobutton(endpoint_frame, text="Azure", variable=self.endpoint_var, value="azure").pack(side=tk.LEFT)
        ttk.Radiobutton(endpoint_frame, text="OpenAI", variable=self.endpoint_var, value="openai").pack(side=tk.LEFT)
        
        # Autoplay
        self.autoplay_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(params_frame, text="Autoplay (no confirmation)", variable=self.autoplay_var).pack(anchor=tk.W, padx=5, pady=2)
        
        # Instructions
        ttk.Label(params_frame, text="Instructions:").pack(anchor=tk.W, padx=5, pady=2)
        self.instructions_var = tk.StringVar(value="Go to https://aka.ms/ldgriev and fill out a grievance and submit it. The name is Mark Smith, the address is 555 Main St., and the delivery date is March 20, 2025. Accept any cookies if a popup arises. Submit the form as soon as it is complete. Do not ask the user for permission to take any action, just take the action.")
        
        self.instructions_text = tk.Text(params_frame, height=5, wrap=tk.WORD, font=('Arial', 12))
        self.instructions_text.pack(fill=tk.X, padx=5, pady=2)
        self.instructions_text.insert(tk.END, self.instructions_var.get())
        
        # User Input area
        self.user_input_frame = ttk.LabelFrame(params_frame, text="User Input")
        self.user_input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create a frame for the input field and submit button
        input_row_frame = ttk.Frame(self.user_input_frame)
        input_row_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # User input field
        self.user_input_var = tk.StringVar()
        self.user_input_field = ttk.Entry(input_row_frame, textvariable=self.user_input_var, font=('Arial', 12))
        self.user_input_field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Bind Enter key to submit
        self.user_input_field.bind("<Return>", self.submit_user_input)
        
        # Submit button
        self.submit_button = ttk.Button(input_row_frame, text="Submit", command=self.submit_user_input)
        self.submit_button.pack(side=tk.RIGHT)
        
        # Disable user input initially
        self.user_input_field.config(state=tk.DISABLED)
        self.submit_button.config(state=tk.DISABLED)
        
        # Start/Stop button
        self.start_button = ttk.Button(params_frame, text="Start", command=self.start_agent)
        self.start_button.pack(fill=tk.X, padx=5, pady=10)
        
    def submit_user_input(self, event=None):
        """Handle user input submission when Submit button is clicked or Enter is pressed"""
        if hasattr(self, 'waiting_for_input') and self.waiting_for_input:
            self.user_input = self.user_input_var.get()
            self.waiting_for_input = False
            self.user_input_field.config(state=tk.DISABLED)
            self.submit_button.config(state=tk.DISABLED)
            self.user_input_var.set("")  # Clear the input field

    def create_central_area(self):
        # VNC output canvas
        self.canvas = tk.Canvas(self.vnc_frame, width=1024, height=768, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind resize events specific to canvas
        self.canvas.bind("<Configure>", self.on_canvas_resize)

    def create_log_area(self):
        log_frame = ttk.LabelFrame(self.controls_frame, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Clear button
        clear_button = ttk.Button(log_frame, text="Clear Log", command=self.clear_log)
        clear_button.pack(anchor=tk.W, padx=5, pady=2)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, state=tk.DISABLED, font=('Arial', 12))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Redirect stdout to the log text widget
        self.text_redirect = RedirectText(self.log_text)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def on_resize(self, event):
        # Only handle resize of the main window
        if event.widget == self.root and self.last_base64_img:
            self.resize_current_image()
    
    def on_canvas_resize(self, event):
        # Handle canvas resize
        if self.last_base64_img:
            self.resize_current_image()
    
    def resize_current_image(self):
        if self.screenshot_image and self.last_base64_img:
            self.update_screenshot(self.last_base64_img, resize_only=True)

    def update_screenshot(self, base64_img, resize_only=False):
        try:
            # Store the base64 image data
            if not resize_only:
                self.last_base64_img = base64_img
                
                # Decode base64 image
                screenshot_data = base64.b64decode(base64_img)
                
                # Convert to PIL Image and store original
                self.screenshot_image = Image.open(io.BytesIO(screenshot_data))
            
            if self.screenshot_image:
                # Get canvas dimensions
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                
                # Ensure we have valid dimensions
                if canvas_width <= 1 or canvas_height <= 1:
                    canvas_width = 1024
                    canvas_height = 768
                
                # Resize image to fit canvas while preserving aspect ratio
                img_width, img_height = self.screenshot_image.size
                aspect_ratio = img_width / img_height
                
                if canvas_width / canvas_height > aspect_ratio:
                    # Canvas is wider than image
                    new_height = canvas_height
                    new_width = int(new_height * aspect_ratio)
                else:
                    # Canvas is taller than image
                    new_width = canvas_width
                    new_height = int(new_width / aspect_ratio)
                
                # Resize image
                resized_img = self.screenshot_image.resize((new_width, new_height), Image.LANCZOS)
                
                # Convert to PhotoImage for display
                self.screenshot_photo = ImageTk.PhotoImage(resized_img)
                
                # Update canvas
                self.canvas.delete("all")
                
                # Calculate position to center the image
                x_offset = (canvas_width - new_width) // 2
                y_offset = (canvas_height - new_height) // 2
                
                # Place the image centered in the canvas
                self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.screenshot_photo)
                
                # Force update
                self.root.update_idletasks()
        except Exception as e:
            print(f"Error updating screenshot: {e}")

    def start_agent(self):
        # Get instructions from text widget
        instructions = self.instructions_text.get(1.0, tk.END).strip()
        self.instructions_var.set(instructions)
        
        if self.running:
            self.running = False
            self.start_button.config(text="Start")
            return
        
        self.running = True
        self.start_button.config(text="Stop")
        
        # Clear log
        self.clear_log()
        
        # Start agent in a separate thread
        thread = threading.Thread(target=self.run_agent)
        thread.daemon = True
        thread.start()

    def run_agent(self):
        # Save the original stdout
        import sys
        original_stdout = sys.stdout
        sys.stdout = self.text_redirect
        
        try:
            # Set up client
            if self.endpoint_var.get() == "azure":
                client = openai.AzureOpenAI(
                    azure_endpoint=os.environ["AZURE_CUA_ENDPOINT"],
                    api_key=os.environ["AZURE_CUA_API_KEY"],
                    api_version="2025-03-01-preview")
            else:
                client = openai.OpenAI()
            
            # Set up computer
            vm_address = self.vm_address_var.get()
            environment = self.environment_var.get()
            
            # Override the screenshot method of VNCComputer to update UI
            class UIVNCComputer(VNCComputer):
                def __init__(self, parent, *args, **kwargs):
                    self.parent = parent
                    super().__init__(*args, **kwargs)
                
                def screenshot(self):
                    image_path = 'screenshot.png'
                    import asyncio
                    asyncio.run(self.vnc.screenshot(screenshot_name=image_path, keys=None))
                    with open(image_path, 'rb') as image_file:
                        data = image_file.read()
                    b64_data = base64.b64encode(data).decode("utf-8")
                    
                    # Update UI with the screenshot
                    self.parent.root.after(0, lambda: self.parent.update_screenshot(b64_data))
                    
                    return b64_data
            
            # Set up computer with custom screenshot method
            self.computer = UIVNCComputer(self, address=vm_address, environment=environment)
            
            # Scaler is used to resize the screen to a smaller size
            size = (1024, 768)
            scaled_computer = cua.Scaler(*size, self.computer)
            
            # Agent to run the CUA model and keep track of state
            self.agent = cua.Agent(client, self.model_var.get(), scaled_computer)
            
            # Get the user request
            user_message = self.instructions_var.get()
            
            print(f"User: {user_message}")
            self.agent.start_task(user_message)
            
            while self.running:
                user_message = None
                if self.agent.requires_consent and not self.autoplay_var.get():
                    # Enable user input for consent
                    print("Agent requires consent. Please provide your response:")
                    self.waiting_for_input = True
                    self.root.after(0, lambda: self.enable_user_input())
                    
                    # Wait for user input
                    while self.waiting_for_input and self.running:
                        time.sleep(0.1)
                    
                    if not self.running:
                        break
                    
                    user_message = self.user_input
                    
                elif self.agent.pending_safety_checks and not self.autoplay_var.get():
                    # Enable user input for safety checks
                    print(f"Safety checks: {self.agent.pending_safety_checks}")
                    print("Please acknowledge these safety checks:")
                    self.waiting_for_input = True
                    self.root.after(0, lambda: self.enable_user_input())
                    
                    # Wait for user input
                    while self.waiting_for_input and self.running:
                        time.sleep(0.1)
                    
                    if not self.running:
                        break
                    
                    user_message = self.user_input
                    
                elif self.agent.requires_user_input:
                    # Enable user input field for agent requests
                    print("Agent requires user input. Please respond:")
                    self.waiting_for_input = True
                    self.root.after(0, lambda: self.enable_user_input())
                    
                    # Wait for user input
                    while self.waiting_for_input and self.running:
                        time.sleep(0.1)
                    
                    if not self.running:
                        break
                    
                    user_message = self.user_input
                
                # Only continue if we're still running
                if self.running:
                    self.agent.continue_task(user_message)
                    print("")
                    if self.agent.reasoning_summary:
                        print(f"Action: {self.agent.reasoning_summary}")
                    if self.agent.message:
                        print(f"Agent: {self.agent.message}")
                        print("")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Restore stdout
            sys.stdout = original_stdout
            self.running = False
            self.root.after(0, lambda: self.start_button.config(text="Start"))
    
    def enable_user_input(self):
        """Enable the user input field and submit button"""
        self.user_input_field.config(state=tk.NORMAL)
        self.submit_button.config(state=tk.NORMAL)
        self.user_input_field.focus()

def main():
    root = tk.Tk()
    app = CUAApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()