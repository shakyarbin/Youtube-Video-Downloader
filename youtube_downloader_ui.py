import yt_dlp
import os
import concurrent.futures
import logging
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import time
import datetime

# Add this import to handle file timestamps
import shutil
import stat

# Set up logging
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        logging.Handler.__init__(self)
        self.text_widget = text_widget
        
    def emit(self, record):
        try:
            msg = self.format(record)
            
            # Clean up ANSI color codes and other terminal escape sequences from the message
            import re
            cleaned_msg = re.sub(r'\x1b\[[0-9;]*m', '', msg)
            
            # Replace emoji characters that might cause display issues
            cleaned_msg = cleaned_msg.replace("🔍", "[Search] ")
            cleaned_msg = cleaned_msg.replace("⬇️", "[Download] ")
            cleaned_msg = cleaned_msg.replace("✅", "[Success] ")
            cleaned_msg = cleaned_msg.replace("❌", "[Error] ")
            cleaned_msg = cleaned_msg.replace("⏱️", "[Time] ")
            cleaned_msg = cleaned_msg.replace("📊", "[Stats] ")
            cleaned_msg = cleaned_msg.replace("📁", "[File] ")
            cleaned_msg = cleaned_msg.replace("📂", "[Folder] ")
            cleaned_msg = cleaned_msg.replace("⚡", "[Speed] ")
            
            def append():
                self.text_widget.config(state=tk.NORMAL)
                # Clear placeholder text if present
                if "Download logs will appear here..." in self.text_widget.get("1.0", tk.END).strip():
                    self.text_widget.delete("1.0", tk.END)
                # Add the log message
                self.text_widget.insert(tk.END, cleaned_msg + '\n')
                self.text_widget.see(tk.END)  # Scroll to show latest message
                self.text_widget.config(state=tk.DISABLED)
            
            # Schedule to be run in the main thread
            self.text_widget.after(0, append)
        except Exception:
            # Catch any exceptions to prevent handler failures
            pass

# Create logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter with shorter format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

# Create file handler with utf-8 encoding
try:
    file_handler = logging.FileHandler('youtube_downloader.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    # If file handler fails, continue without it
    pass

# The console handler will be added after the UI is created

def check_ffmpeg():
    """Check if FFmpeg is installed and accessible"""
    try:
        import ffmpeg
        return True
    except Exception:
        try:
            # Attempt to run ffmpeg command
            import subprocess
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except Exception as e:
            logging.error(f"FFmpeg not found: {str(e)}")
            return False

class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, radius=25, **kwargs):
        # Remove fg from kwargs as Canvas doesn't support it
        self.fg = kwargs.pop('fg', 'black')
        # Handle other custom attributes
        self.bg = kwargs.pop('bg', 'white')
        self.hover_bg = kwargs.pop('hover_bg', '#e9ecef')
        self.active_bg = kwargs.pop('active_bg', '#dee2e6')
        self.font = kwargs.pop('font', ("Inter", 11))  # Updated font
        
        # Initialize canvas with remaining kwargs
        super().__init__(parent, **kwargs)
        
        self.command = command
        self.radius = radius
        self.text = text
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<ButtonRelease-1>", self.on_release)
        
        self.draw_button()
    
    def draw_button(self, bg=None):
        if bg is None:
            bg = self.bg
        
        self.delete("all")
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        
        # Draw rounded rectangle
        self.create_roundrect(0, 0, width, height, self.radius, fill=bg, outline='')
        
        # Draw text
        self.create_text(width/2, height/2, text=self.text, fill=self.fg, font=self.font)
    
    def create_roundrect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius, y1,
                 x2-radius, y1,
                 x2, y1,
                 x2, y1+radius,
                 x2, y2-radius,
                 x2, y2,
                 x2-radius, y2,
                 x1+radius, y2,
                 x1, y2,
                 x1, y2-radius,
                 x1, y1+radius,
                 x1, y1]
        return self.create_polygon(points, smooth=True, **kwargs)
    
    def on_enter(self, event):
        self.draw_button(self.hover_bg)
    
    def on_leave(self, event):
        self.draw_button(self.bg)
    
    def on_click(self, event):
        self.draw_button(self.active_bg)
        if self.command:
            self.command()
    
    def on_release(self, event):
        self.draw_button(self.hover_bg)

class RoundedProgressBar(tk.Canvas):
    def __init__(self, parent, width=400, height=24, **kwargs):
        self.width = width
        self.height = height
        self.radius = height // 2
        self.progress = 0
        self.target_progress = 0
        self.animation_speed = 2.0  # Speed of animation (higher = faster)
        self.bg_color = kwargs.pop('bg_color', "#f0f5f9")
        self.fg_color = kwargs.pop('fg_color', "#4CAF50")
        self.border_color = kwargs.pop('border_color', "#e1e1e1")
        
        super().__init__(parent, width=width, height=height, 
                         highlightthickness=0, **kwargs)
        self.draw_progress()
        
        # For smooth animation
        self.after_id = None
    
    def draw_progress(self):
        self.delete("all")
        # Draw background rounded rectangle
        self.create_roundrect(0, 0, self.width, self.height, self.radius, 
                             fill=self.bg_color, outline=self.border_color)
        
        if self.progress > 0:
            # Calculate progress width
            progress_width = (self.width * self.progress) / 100
            
            # Don't let progress exceed the width
            progress_width = min(progress_width, self.width)
            
            # Draw progress rounded rectangle
            if progress_width <= self.radius * 2:
                # Special case for very small progress (draw partial circle)
                self.create_roundrect(0, 0, progress_width, self.height, 
                                     self.radius, fill=self.fg_color, outline="")
            else:
                # Draw normal rounded rectangle for progress
                self.create_roundrect(0, 0, progress_width, self.height, 
                                     self.radius, fill=self.fg_color, outline="")
    
    def create_roundrect(self, x1, y1, x2, y2, radius, **kwargs):
        # Draw rounded rectangle
        points = [
            x1+radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1
        ]
        return self.create_polygon(points, smooth=True, **kwargs)
    
    def set_progress(self, progress):
        """Set target progress and start animation if not already animating"""
        self.target_progress = progress
        
        # Cancel any existing animation
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        
        # Start animation
        self._animate_progress()
    
    def _animate_progress(self):
        """Animate progress bar smoothly"""
        if abs(self.progress - self.target_progress) < 0.5:
            # If close enough, just set to target
            self.progress = self.target_progress
            self.draw_progress()
            self.after_id = None
            return
        
        # Move towards target
        diff = self.target_progress - self.progress
        step = diff * (self.animation_speed / 10)
        
        # Ensure minimum step size for visible progress
        if abs(step) < 0.5:
            step = 0.5 if diff > 0 else -0.5
            
        self.progress += step
        self.draw_progress()
        
        # Continue animation
        self.after_id = self.after(16, self._animate_progress)  # ~60fps

class VideoCard(ttk.Frame):
    """A card representing a video in a playlist"""
    def __init__(self, parent, video_info, index, **kwargs):
        # Create a frame with custom styling for a card-like appearance
        super().__init__(parent, **kwargs)
        
        self.video_info = video_info
        self.index = index
        self.download_status = "pending"  # pending, downloading, completed, error
        
        # Configure grid
        self.columnconfigure(0, weight=1)  # Title and info
        self.columnconfigure(1, weight=0)  # Status indicators
        
        # Get video info
        self.title = video_info.get('title', f"Video {index+1}")
        self.duration = video_info.get('duration_string', '--')
        self.filesize = video_info.get('filesize_approx_str', '--')
        
        # Get more detailed info if available
        self.channel = video_info.get('channel', video_info.get('uploader', '--'))
        self.upload_date = video_info.get('upload_date', '--')
        if self.upload_date and len(self.upload_date) == 8:
            year, month, day = self.upload_date[0:4], self.upload_date[4:6], self.upload_date[6:8]
            self.upload_date = f"{year}-{month}-{day}"
        
        self.views = video_info.get('view_count', '--')
        if isinstance(self.views, int) and self.views > 1000:
            if self.views > 1000000:
                self.views = f"{self.views/1000000:.1f}M views"
            else:
                self.views = f"{self.views/1000:.1f}K views"
        elif self.views != '--':
            self.views = f"{self.views} views"
        
        # Create a custom card container with rounded corners and shadow effect
        # First, create a canvas for the shadow effect
        shadow_frame = tk.Frame(self, bg="#E6E6E6", padx=2, pady=2)
        shadow_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        # Inside the shadow frame, create the actual card content
        card_content = tk.Frame(shadow_frame, bg="white", padx=10, pady=10)
        card_content.pack(fill=tk.BOTH, expand=True)
        
        # Create title label with thumbnail placeholder
        title_frame = tk.Frame(card_content, bg="white")
        title_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Index number in a circular badge
        index_badge = tk.Canvas(title_frame, width=24, height=24, bg="white", highlightthickness=0)
        index_badge.create_oval(2, 2, 22, 22, fill="#FF0000", outline="")
        index_badge.create_text(12, 12, text=f"{index+1}", fill="white", font=("Inter", 10, "bold"))
        index_badge.pack(side=tk.LEFT, padx=(0, 8))
        
        # Title (truncated if too long)
        display_title = self.title
        if len(display_title) > 50:
            display_title = display_title[:47] + "..."
        
        self.title_label = tk.Label(title_frame, text=display_title, 
                                  font=("Inter", 11, "bold"), 
                                  anchor="w", justify="left",
                                  bg="white", fg="#333333",
                                  wraplength=350)
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Info panel with cleaner layout
        info_panel = tk.Frame(card_content, bg="white")
        info_panel.pack(fill=tk.X, pady=5)
        
        # Channel info with icon
        channel_frame = tk.Frame(info_panel, bg="white")
        channel_frame.pack(fill=tk.X, pady=(0, 5))
        
        channel_label = tk.Label(channel_frame, text=f"👤 {self.channel}", 
                               font=("Inter", 9), bg="white")
        channel_label.pack(side=tk.LEFT, padx=(5, 10))
        
        if self.upload_date != '--':
            date_label = tk.Label(channel_frame, text=f"📅 {self.upload_date}", 
                                font=("Inter", 9), bg="white")
            date_label.pack(side=tk.LEFT)
        
        # Second row with duration, size, views
        stats_frame = tk.Frame(info_panel, bg="white")
        stats_frame.pack(fill=tk.X)
        
        duration_label = tk.Label(stats_frame, text=f"⏱️ {self.duration}", 
                                font=("Inter", 9), bg="white")
        duration_label.pack(side=tk.LEFT, padx=(5, 10))
        
        size_label = tk.Label(stats_frame, text=f"📊 {self.filesize}", 
                           font=("Inter", 9), bg="white")
        size_label.pack(side=tk.LEFT, padx=(0, 10))
        
        if self.views != '--':
            views_label = tk.Label(stats_frame, text=f"👁️ {self.views}", 
                                font=("Inter", 9), bg="white")
            views_label.pack(side=tk.LEFT)
        
        # Status section on the right
        status_frame = tk.Frame(card_content, bg="white")
        status_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.status_var = tk.StringVar(value="⏳ Pending")
        self.status_label = tk.Label(status_frame, textvariable=self.status_var, 
                                  font=("Inter", 10, "bold"), bg="white")
        self.status_label.pack(side=tk.LEFT, pady=(0, 5))
        
        # Progress bar with custom styling
        self.progress_frame = tk.Frame(card_content, bg="white")
        self.progress_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.progress_bar = RoundedProgressBar(
            self.progress_frame,
            width=400,
            height=16,
            bg_color="#f0f5f9",
            fg_color="#4CAF50",
            border_color="#e1e1e1"
        )
        self.progress_bar.pack(fill=tk.X, expand=True)
    
    def update_progress(self, percent, status=None):
        """Update the progress bar and status"""
        self.progress_bar.set_progress(percent)
        
        if status:
            self.download_status = status
            
            if status == "downloading":
                self.status_var.set(f"⬇️ {int(percent)}%")
                self.status_label.config(fg="#4CAF50")  # Green for active download
            elif status == "completed":
                self.status_var.set("✅ Completed")
                self.status_label.config(fg="#4CAF50")  # Green for success
            elif status == "error":
                self.status_var.set("❌ Failed")
                self.status_label.config(fg="#FF0000")  # Red for error
            else:
                self.status_var.set("⏳ Pending")
                self.status_label.config(fg="#FF9800")  # Orange for pending

class PlaylistView(ttk.Frame):
    """A scrollable frame that displays all videos in a playlist"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        # Configure grid
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Create a canvas for scrolling
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # Add scrollbar
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Create frame inside canvas for video cards
        self.video_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.video_frame, anchor="nw")
        
        # Configure video frame
        self.video_frame.columnconfigure(0, weight=1)
        
        # Bind events for scrolling
        self.video_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Store video cards
        self.video_cards = []
        
        # Empty state label
        self.empty_label = ttk.Label(self.video_frame, text="No videos in playlist", font=("Inter", 12))
        self.empty_label.grid(row=0, column=0, padx=20, pady=20)
    
    def _on_frame_configure(self, event):
        """Update the canvas scroll region when the frame changes size"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """Update the width of the frame inside the canvas when canvas changes size"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def clear(self):
        """Clear all video cards"""
        for widget in self.video_frame.winfo_children():
            widget.destroy()
        
        self.video_cards = []
        
        # Show empty state
        self.empty_label = ttk.Label(self.video_frame, text="No videos in playlist", font=("Inter", 12))
        self.empty_label.grid(row=0, column=0, padx=20, pady=20)
    
    def add_video(self, video_info, index):
        """Add a video card to the playlist view"""
        # Remove empty label if this is the first video
        if index == 0:
            for widget in self.video_frame.winfo_children():
                widget.destroy()
        
        # Create video card
        card = VideoCard(self.video_frame, video_info, index, style="Card.TFrame")
        card.grid(row=index, column=0, sticky="ew", padx=5, pady=5)
        
        self.video_cards.append(card)
        return card
    
    def update_video_progress(self, index, percent, status=None):
        """Update the progress of a specific video"""
        if 0 <= index < len(self.video_cards):
            self.video_cards[index].update_progress(percent, status)

class DescriptionPanel(ttk.Frame):
    """A panel to display video metadata details"""
    def __init__(self, parent, **kwargs):
        # Initialize ttk.Frame with proper parameters
        super().__init__(parent, **kwargs)
        
        # Set colors for text elements - these will be used for the text widget only, not the frame
        self.bg_color = '#F8F8F8'
        self.text_color = '#333333'
        
        # Create header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        title_label = ttk.Label(header_frame, text="Description", font=("Inter", 14, "bold"))
        title_label.pack(side=tk.LEFT)
        
        self.count_label = ttk.Label(header_frame, text="", font=("Inter", 12))
        self.count_label.pack(side=tk.RIGHT)
        
        # Create scrollable text area for description
        self.description_text = tk.Text(self, wrap=tk.WORD, 
                                     height=10, 
                                     bg=self.bg_color, 
                                     fg=self.text_color,
                                     font=("Inter", 11),
                                     relief=tk.FLAT,
                                     padx=10,
                                     pady=10)
        self.description_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(self.description_text, command=self.description_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.description_text.config(yscrollcommand=scrollbar.set)
        
        # Placeholder text
        self.description_text.insert(tk.END, "Video information will appear here when you search for a video or playlist.")
        self.description_text.config(state=tk.DISABLED)
    
    def update_description(self, info):
        """Update the description with video metadata"""
        self.description_text.config(state=tk.NORMAL)
        self.description_text.delete(1.0, tk.END)
        
        if not info:
            self.description_text.insert(tk.END, "No video information available")
            self.count_label.config(text="")
            self.description_text.config(state=tk.DISABLED)
            return
        
        # Check if it's a playlist or single video
        if isinstance(info, list):
            # It's a list of videos (playlist)
            self.count_label.config(text=f"{len(info)} videos")
            
            for i, video in enumerate(info):
                self._add_video_info(video, index=i+1)
                
                # Add separator between videos
                if i < len(info) - 1:
                    self.description_text.insert(tk.END, "\n" + "-"*50 + "\n\n")
        else:
            # Single video
            self.count_label.config(text="1 video")
            self._add_video_info(info)
        
        self.description_text.config(state=tk.DISABLED)
        self.description_text.see("1.0")  # Scroll to top
    
    def _add_video_info(self, video, index=None):
        """Add a single video's information to the description"""
        if not video:
            return
            
        # Title with optional numbering
        if index is not None:
            self.description_text.insert(tk.END, f"{index}. ", "bold")
        
        title = video.get('title', 'Unknown Title')
        self.description_text.insert(tk.END, f"{title}\n", "bold")
        
        # Channel/uploader
        uploader = video.get('uploader', video.get('channel', 'Unknown Channel'))
        self.description_text.insert(tk.END, f"Channel: {uploader}\n")
        
        # Duration
        duration = video.get('duration_string', video.get('duration', '--'))
        self.description_text.insert(tk.END, f"Duration: {duration}\n")
        
        # Upload date
        upload_date = video.get('upload_date', '--')
        if upload_date and len(str(upload_date)) == 8:
            year, month, day = upload_date[0:4], upload_date[4:6], upload_date[6:8]
            upload_date = f"{year}-{month}-{day}"
        self.description_text.insert(tk.END, f"Upload date: {upload_date}\n")
        
        # Views
        views = video.get('view_count', '--')
        if isinstance(views, int) and views > 1000:
            if views > 1000000:
                views = f"{views/1000000:.1f}M views"
            else:
                views = f"{views/1000:.1f}K views"
        elif views != '--':
            views = f"{views} views"
        self.description_text.insert(tk.END, f"Views: {views}\n")
        
        # Description (truncated)
        description = video.get('description', '')
        if description:
            # Truncate long descriptions
            if len(description) > 300:
                description = description[:297] + "..."
            self.description_text.insert(tk.END, f"\nDescription: {description}\n")

class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader")
        self.root.geometry("700x1000")  # Increased height for better playlist display
        self.root.resizable(True, True)
        self.root.configure(bg="white")
        
        # Enable font antialiasing
        try:
            # Try to enable font antialiasing on Windows
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        # Define fonts - Use a clean, minimal font
        self.title_font = ("Inter", 16, "bold")
        self.normal_font = ("Inter", 11)
        self.small_font = ("Inter", 10)
        self.button_font = ("Inter", 11, "bold")
        
        # Define colors with a minimalist palette
        self.bg_color = "white"
        self.card_bg = "white"
        self.accent_color = "#FF0000"  # YouTube red
        self.text_color = "#333333"    # Dark gray for text
        self.light_bg = "#F8F8F8"      # Very light gray
        self.border_color = "#E6E6E6"  # Light gray borders
        self.button_bg = "#4CAF50"     # Green for buttons
        self.button_hover = "#45a049"  # Darker green for hover
        self.button_active = "#3d8b40" # Even darker for active state
        
        # Configure styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure widget styles
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        
        self.style.configure("TLabel", 
                          background=self.card_bg, 
                          foreground=self.text_color, 
                          font=self.normal_font)
        
        self.style.configure("Title.TLabel", 
                          background=self.card_bg, 
                          foreground=self.text_color, 
                          font=self.title_font)
        
        # Configure circular radio buttons with accent color
        self.style.configure("TRadiobutton", 
                          background=self.card_bg, 
                          foreground=self.text_color, 
                          font=self.normal_font,
                          padding=10,  # Added padding for better spacing
                          indicatordiameter=20,  # Larger indicator for better visibility
                          indicatorrelief='flat',  # Flat appearance
                          indicatorborderwidth=2,  # Thinner border
                          indicatorbackground='white',  # White background
                          indicatorforeground=self.accent_color)  # Accent color for selected state

        # Customize the circular appearance and colors
        self.style.map("TRadiobutton",
                    background=[('active', self.card_bg)],
                    foreground=[('active', self.accent_color)],
                    indicatorcolor=[('selected', self.accent_color), 
                                   ('!selected', 'white')],
                    indicatorrelief=[('selected', 'flat')],
                    relief=[('active', 'flat')],
                    borderwidth=[('selected', 2)])

        # Create a custom layout for radio buttons
        self.style.layout("TRadiobutton",
            [('Radiobutton.padding',
                {'children': [('Radiobutton.indicator', {'side': 'left', 'sticky': ''}),
                            ('Radiobutton.focus',
                                {'children': [('Radiobutton.label', {'sticky': 'nswe'})],
                                'side': 'left', 'sticky': ''})],
                'sticky': 'nswe'})])
        
        # Add small button style for history items
        self.style.configure("Small.TButton", 
                          font=self.small_font, 
                          padding=2)
        
        self.style.configure("Horizontal.TProgressbar", 
                          background=self.accent_color,
                          troughcolor=self.light_bg,
                          borderwidth=0)
        
        # Main frame for all content
        main_frame = ttk.Frame(root, style="TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Create a canvas for the card with a scrollbar
        self.card_frame = ttk.Frame(main_frame, style="Card.TFrame", relief="solid", borderwidth=1)
        self.card_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title with minimalist logo
        title_frame = ttk.Frame(self.card_frame, style="Card.TFrame")
        title_frame.pack(fill=tk.X, padx=20, pady=(30, 20))
        
        # Draw minimal red triangle for logo
        triangle_size = 12
        logo_canvas = tk.Canvas(title_frame, width=triangle_size, height=triangle_size, bg=self.card_bg, highlightthickness=0)
        logo_canvas.create_polygon(0, 0, triangle_size, triangle_size/2, 0, triangle_size, fill="#FF0000")
        logo_canvas.pack(side=tk.LEFT, padx=(5, 10))
        
        # Simple, clean title text
        title_label = ttk.Label(title_frame, text="YouTube Downloader", font=("Inter", 18, "bold"), foreground="#FF0000")
        title_label.pack(side=tk.LEFT)
        
        # Content frame
        content_frame = ttk.Frame(self.card_frame, style="Card.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # URL input with search button
        url_label = ttk.Label(content_frame, text="YouTube URL", font=("Inter", 11))
        url_label.pack(anchor=tk.W, pady=(10, 5))
        
        url_frame = ttk.Frame(content_frame)
        url_frame.pack(fill=tk.X, pady=(0, 20))  # Increased spacing
        
        self.url_entry = tk.Entry(url_frame,
                                font=self.normal_font,
                                bg="white",
                                fg=self.text_color,
                                relief=tk.FLAT,
                                bd=1,
                                highlightthickness=1,
                                highlightbackground=self.border_color,
                                highlightcolor=self.accent_color)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.url_entry.insert(0, "Paste YouTube URL here...")
        self.url_entry.bind("<FocusIn>", self.clear_placeholder)
        self.url_entry.bind("<FocusOut>", self.restore_placeholder)
        
        # Add search button
        self.search_button = RoundedButton(url_frame,
                                       text="Search",  # Removed emoji for minimalism
                                       width=100,
                                       height=30,
                                       bg=self.accent_color,
                                       fg="white",
                                       hover_bg="#E60000",  # Slightly darker red
                                       active_bg="#CC0000",  # Even darker red
                                       font=self.normal_font,
                                       command=self.search_videos)
        self.search_button.pack(side=tk.RIGHT)
        
        # After URL entry and before Quality selection, add save location section
        save_label = ttk.Label(content_frame, text="Save Location")
        save_label.pack(anchor=tk.W, pady=(0, 5))
        
        save_frame = ttk.Frame(content_frame, style="Card.TFrame")
        save_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Default save location
        self.save_location = str(Path.home() / "Downloads")
        
        # Save location entry
        self.save_entry = tk.Entry(save_frame,
                                font=self.normal_font,
                                bg="white",
                                fg=self.text_color,
                                relief=tk.FLAT,
                                bd=1,
                                highlightthickness=1,
                                highlightbackground=self.border_color,
                                highlightcolor=self.accent_color)
        self.save_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.save_entry.insert(0, self.save_location)
        
        # Browse button
        self.browse_button = RoundedButton(save_frame,
                                       text="📁 Browse",
                                       width=100,
                                       height=30,
                                       bg=self.light_bg,
                                       fg=self.text_color,
                                       hover_bg="#e9ecef",
                                       active_bg="#dee2e6",
                                       font=self.normal_font,
                                       command=self.browse_location)
        self.browse_button.pack(side=tk.RIGHT)
        
        # Open folder button next to browse button
        self.open_folder_button = RoundedButton(save_frame,
                                       text="📂 Open",
                                       width=100,
                                       height=30,
                                       bg=self.light_bg,
                                       fg=self.text_color,
                                       hover_bg="#e9ecef",
                                       active_bg="#dee2e6",
                                       font=self.normal_font,
                                       command=lambda: self.open_folder(self.save_location))
        self.open_folder_button.pack(side=tk.RIGHT, padx=(0, 5))
        
        # Replace the separate quality and format sections with a combined layout
        # Create a container frame for both quality and format sections
        format_quality_container = ttk.Frame(content_frame, style="Card.TFrame")
        format_quality_container.pack(fill=tk.X, pady=(0, 15))

        # Left side - Quality selection
        quality_frame = ttk.Frame(format_quality_container, style="Card.TFrame")
        quality_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        quality_label = ttk.Label(quality_frame, text="Select Quality", font=("Inter", 11, "bold"))
        quality_label.pack(anchor=tk.W, pady=(0, 5))

        self.quality_var = tk.StringVar(value="720p")

        # Quality radio buttons
        quality_radio_frame = ttk.Frame(quality_frame, style="Card.TFrame")
        quality_radio_frame.pack(fill=tk.X, expand=True)

        # 360p option
        ttk.Radiobutton(quality_radio_frame, text="360p", variable=self.quality_var, value="360p").pack(side=tk.LEFT, padx=(5, 15), pady=10)

        # 720p option (default)
        ttk.Radiobutton(quality_radio_frame, text="720p", variable=self.quality_var, value="720p").pack(side=tk.LEFT, padx=(0, 15), pady=10)

        # 1080p option
        ttk.Radiobutton(quality_radio_frame, text="1080p", variable=self.quality_var, value="1080p").pack(side=tk.LEFT, padx=(0, 5), pady=10)

        # Right side - Format selection
        format_frame = ttk.Frame(format_quality_container, style="Card.TFrame")
        format_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        format_label = ttk.Label(format_frame, text="Select Format", font=("Inter", 11, "bold"))
        format_label.pack(anchor=tk.W, pady=(0, 5))

        self.format_var = tk.StringVar(value="video")

        # Format radio buttons
        radio_frame = ttk.Frame(format_frame, style="Card.TFrame")
        radio_frame.pack(fill=tk.X, expand=True)

        # Video+Audio option
        video_radio = ttk.Radiobutton(radio_frame, text="Video+Audio", variable=self.format_var, value="video")
        video_radio.pack(side=tk.LEFT, padx=(5, 15), pady=10)

        # Audio Only option
        audio_radio = ttk.Radiobutton(radio_frame, text="Audio Only", variable=self.format_var, value="audio")
        audio_radio.pack(side=tk.LEFT, padx=(0, 5), pady=10)

        # Store format buttons for reference
        self.format_buttons = {"video": video_radio, "audio": audio_radio}
        
        # Subtitles option
        subtitle_frame = ttk.Frame(content_frame, style="Card.TFrame")
        subtitle_frame.pack(fill=tk.X, pady=(0, 15))
        
        subtitle_label = ttk.Label(subtitle_frame, text="Include Subtitles")
        subtitle_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.subtitle_var = tk.BooleanVar(value=False)
        subtitle_check = ttk.Checkbutton(subtitle_frame, variable=self.subtitle_var)
        subtitle_check.pack(side=tk.RIGHT)
        
        # Playlist option
        playlist_frame = ttk.Frame(content_frame, style="Card.TFrame")
        playlist_frame.pack(fill=tk.X, pady=(0, 15))
        
        playlist_label = ttk.Label(playlist_frame, text="Playlist Mode")
        playlist_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.playlist_var = tk.BooleanVar(value=False)
        self.playlist_switch = ttk.Checkbutton(playlist_frame, variable=self.playlist_var)
        self.playlist_switch.pack(side=tk.RIGHT)
        
        # Download progress section
        progress_label = ttk.Label(content_frame, text="Download Progress")
        progress_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Custom rounded progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = RoundedProgressBar(
            content_frame,
            width=580,
            height=24,
            bg_color=self.light_bg,
            fg_color=self.accent_color,
            border_color=self.border_color
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Stats frame
        stats_frame = ttk.Frame(content_frame, style="Card.TFrame")
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Create a structured grid for stats to ensure proper spacing
        stats_frame.columnconfigure(0, weight=1)  # ETA
        stats_frame.columnconfigure(1, weight=1)  # Speed
        stats_frame.columnconfigure(2, weight=1)  # Percentage

        # Left side - ETA
        self.eta_var = tk.StringVar(value="ETA: --")
        eta_label = ttk.Label(stats_frame, textvariable=self.eta_var, anchor="w")
        eta_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        # Center - Speed
        self.speed_var = tk.StringVar(value="Speed: --")
        speed_label = ttk.Label(stats_frame, textvariable=self.speed_var, anchor="center")
        speed_label.grid(row=0, column=1, sticky="ew", padx=10)

        # Right side - Percentage
        self.percent_var = tk.StringVar(value="0%")
        percent_label = ttk.Label(stats_frame, textvariable=self.percent_var, anchor="e")
        percent_label.grid(row=0, column=2, sticky="e", padx=(10, 0))

        # Configure row weight to center vertically
        stats_frame.rowconfigure(0, weight=1)
        
        # Downloads counter
        downloads_frame = ttk.Frame(content_frame, style="Card.TFrame")
        downloads_frame.pack(fill=tk.X, pady=(0, 15))
        
        downloads_icon = ttk.Label(downloads_frame, text="🎯", font=("Segoe UI", 12), background=self.card_bg)
        downloads_icon.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.downloads_var = tk.StringVar(value="Downloads: 0")
        downloads_label = ttk.Label(downloads_frame, textvariable=self.downloads_var)
        downloads_label.pack(side=tk.RIGHT)
        
        # Buttons frame with more prominent download button
        buttons_frame = ttk.Frame(content_frame, style="Card.TFrame")
        buttons_frame.pack(fill=tk.X, pady=(10, 20))
        
        # Download button with green styling - increased width to ensure it's visible
        self.download_button = RoundedButton(
            buttons_frame,
            text="Download",  # Removed emoji for minimalism
            width=400,
            height=50,
            bg=self.button_bg, 
            fg="white",
            hover_bg=self.button_hover,
            active_bg=self.button_active,
            font=("Inter", 12, "bold"),
            command=self.start_download
        )
        self.download_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Clear button with matching style
        self.clear_button = RoundedButton(
            buttons_frame,
            text="Clear",  # Removed emoji for minimalism
            width=150,
            height=50,
            bg="#f8f9fa",
            fg=self.text_color,
            hover_bg="#e9ecef",
            active_bg="#dee2e6",
            font=("Inter", 11),
            command=self.clear_form
        )
        self.clear_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Create log frame after description frame
        log_label = ttk.Label(content_frame, text="Download Log", font=("Inter", 11, "bold"))
        log_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Create a frame for the log area with proper styling
        log_frame = ttk.Frame(content_frame, style="Card.TFrame", relief="solid", borderwidth=1)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create text widget for logs with improved styling - increase height for better visibility
        self.log_text = tk.Text(log_frame,
                    height=12,  # Increased height for better visibility
                    wrap=tk.WORD,
                    font=self.normal_font,
                    bg=self.light_bg,
                    fg=self.text_color,
                    relief=tk.FLAT,
                    padx=10,
                    pady=10)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_text.insert(tk.END, "Download logs will appear here...\n")
        self.log_text.config(state=tk.DISABLED)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Add button to clear logs
        log_controls_frame = ttk.Frame(log_frame)
        log_controls_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        
        clear_logs_button = ttk.Button(
            log_controls_frame,
            text="Clear Logs",
            command=self.clear_logs
        )
        clear_logs_button.pack(side=tk.RIGHT)
        
        # Download status tracking
        self.is_downloading = False
        self.download_thread = None
        self.download_count = 0
        
        # Create console handler after UI is initialized
        console_handler = TextHandler(self.log_text)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # After the log and before the buttons frame
        # Playlist view (hidden by default)
        self.playlist_view_frame = ttk.Frame(content_frame, style="Card.TFrame")
        self.playlist_view_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        self.playlist_view_frame.pack_forget()  # Hide initially
        
        playlist_title_frame = ttk.Frame(self.playlist_view_frame)
        playlist_title_frame.pack(fill=tk.X, padx=5, pady=5)
        
        playlist_label = ttk.Label(playlist_title_frame, text="Playlist Videos", font=("Inter", 12, "bold"))
        playlist_label.pack(side=tk.LEFT)
        
        self.playlist_info_var = tk.StringVar(value="")
        playlist_info = ttk.Label(playlist_title_frame, textvariable=self.playlist_info_var, font=("Inter", 10))
        playlist_info.pack(side=tk.RIGHT)
        
        self.playlist_view = PlaylistView(self.playlist_view_frame)
        self.playlist_view.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Store playlist info
        self.current_playlist_info = None
        self.current_playlist_videos = []
        self.current_video_index = -1
        
        # Update playlist switch to toggle view
        self.playlist_var.trace_add("write", lambda *args: self.playlist_toggle())
        
        # Add this near other initialization variables
        self.progress_lock = threading.Lock()  # Lock for updating progress safely
        self.download_pool = None  # Thread pool for parallel downloads
        
        # Add download history section
        history_label = ttk.Label(content_frame, text="Recent Downloads")
        history_label.pack(anchor=tk.W, pady=(15, 5))
        
        self.download_history_frame = ttk.Frame(content_frame, style="Card.TFrame", relief="solid", borderwidth=1)
        self.download_history_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Initialize download history list
        self.download_history = []
        
        # Show initial empty state
        empty_label = ttk.Label(self.download_history_frame, text="No recent downloads", font=self.normal_font)
        empty_label.pack(pady=10)
    
    def create_roundrect(self, canvas, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius, y1,
                 x2-radius, y1,
                 x2, y1,
                 x2, y1+radius,
                 x2, y2-radius,
                 x2, y2,
                 x2-radius, y2,
                 x1+radius, y2,
                 x1, y2,
                 x1, y2-radius,
                 x1, y1+radius,
                 x1, y1]
        return canvas.create_polygon(points, smooth=True, **kwargs)
    
    def set_format(self, format_type):
        """Update the format selection"""
        self.format_var.set(format_type)
        # No need to update button styles as radio buttons handle their own state
    
    def clear_placeholder(self, event):
        """Clear placeholder text when entry gains focus"""
        if self.url_entry.get() == "Paste YouTube URL here...":
            self.url_entry.delete(0, tk.END)
    
    def restore_placeholder(self, event):
        """Restore placeholder text when entry loses focus and is empty"""
        if not self.url_entry.get():
            self.url_entry.insert(0, "Paste YouTube URL here...")
    
    def clear_form(self):
        """Reset the form to default state"""
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, "Paste YouTube URL here...")
        self.quality_var.set("720p")
        self.format_var.set("video")
        self.set_format("video")
        self.subtitle_var.set(False)
        self.playlist_var.set(False)
        self.progress_var.set(0)
        self.percent_var.set("0%")
        self.eta_var.set("ETA: --")
        self.speed_var.set("Speed: --")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, "Download actions will appear here...")
        self.log_text.config(state=tk.DISABLED)
    
    def log_message(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)  # Clear placeholder
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def update_status(self, status):
        """Update status in log area with improved formatting and visibility"""
        # Clean any terminal escape sequences from the status message
        if isinstance(status, str):
            # Remove ANSI color codes and other terminal escape sequences
            import re
            status = re.sub(r'\x1b\[[0-9;]*m', '', status)
            # Remove URLs from error messages for cleaner display
            status = re.sub(r'See\s+https?://[^\s]+', '', status)
            status = re.sub(r'Also see\s+https?://[^\s]+', '', status)
            # Clean up YouTube error messages
            status = status.replace("ERROR:", "Error:").replace("youtube:", "YouTube:")
            status = status.replace("Use --cookies-from-browser or --cookies for the authentication.", "")
            
            # Replace emoji characters that might cause display issues with plain text alternatives
            status = status.replace("🔍", "[Search] ")
            status = status.replace("⬇️", "[Download] ")
            status = status.replace("✅", "[Success] ")
            status = status.replace("❌", "[Error] ")
            status = status.replace("⏱️", "[Time] ")
            status = status.replace("📊", "[Stats] ")
            status = status.replace("📁", "[File] ")
            status = status.replace("📂", "[Folder] ")
            status = status.replace("⚡", "[Speed] ")
        
        try:
            # Log message to file (if possible)
            logger.info(status)
        except Exception:
            # If logging fails (e.g., due to encoding issues), continue without logging to file
            pass
        
        # Always update the UI text widget
        self.log_text.config(state=tk.NORMAL)
        
        # First time message - clear placeholder
        if self.log_text.get("1.0", tk.END).strip() == "Download logs will appear here...":
            self.log_text.delete("1.0", tk.END)
            
        # Add timestamp to new messages
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Add message with timestamp
        self.log_text.insert(tk.END, f"[{timestamp}] {status}\n")
        self.log_text.see(tk.END)  # Scroll to show latest message
        self.log_text.config(state=tk.DISABLED)
        
        # Force update the UI
        self.root.update_idletasks()
    
    def update_progress(self, progress):
        """Update progress bar and percentage text"""
        progress = float(progress)
        self.progress_bar.set_progress(progress)
        self.percent_var.set(f"{int(progress)}%")
        self.root.update_idletasks()
    
    def update_download_count(self):
        """Increment download counter"""
        self.download_count += 1
        self.downloads_var.set(f"Downloads: {self.download_count}")
    
    def browse_location(self):
        """Open folder browser to select save location"""
        folder = filedialog.askdirectory(
            initialdir=self.save_location,
            title="Select Save Location"
        )
        if folder:
            self.save_location = folder
            self.save_entry.delete(0, tk.END)
            self.save_entry.insert(0, folder)
            logging.info(f"Save location changed to: {folder}")
    
    def start_download(self):
        # Validate input
        url = self.url_entry.get().strip()
        if url == "Paste YouTube URL here..." or not url:
            messagebox.showerror("Error", "Please enter a YouTube URL")
            return
        
        # Get selected options
        quality = self.quality_var.get()
        format_type = self.format_var.get()
        include_subs = self.subtitle_var.get()
        download_type = "playlist" if self.playlist_var.get() else "single"
        
        # Get save location
        output_dir = self.save_location
        
        # Check if directory exists, create if it doesn't
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                logging.info(f"Created output directory: {output_dir}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not create save directory:\n{str(e)}")
                return
        
        # Check if directory is writable
        if not os.access(output_dir, os.W_OK):
            messagebox.showerror("Error", "Save location is not writable")
            return
        
        # Check FFmpeg
        if not check_ffmpeg():
            messagebox.showerror("Error", "FFmpeg is required but not found. Please install FFmpeg and try again.")
            return
        
        # Update UI state
        self.is_downloading = True
        self.download_button.config(state=tk.DISABLED)
        self.download_button.bg = "#6c757d"
        self.download_button.draw_button("#6c757d")
        
        # Check if it's a playlist and fetch info first if needed
        if self.playlist_var.get() and not self.current_playlist_info:
            threading.Thread(target=self.fetch_playlist_info, args=(url,), daemon=True).start()
            return
        
        # Start download in a separate thread
        self.download_thread = threading.Thread(
            target=self.download_task,
            args=(url, download_type, quality, format_type, include_subs, output_dir)
        )
        self.download_thread.daemon = True
        self.download_thread.start()
        
        # Start progress monitoring
        self.root.after(100, self.check_download_progress)
    
    def check_download_progress(self):
        if self.is_downloading and self.download_thread.is_alive():
            self.root.after(100, self.check_download_progress)
        else:
            if not self.is_downloading:
                self.update_status("Download cancelled")
            else:
                self.update_status("Download completed")
                self.update_download_count()
            
            self.is_downloading = False
            self.download_button.config(state=tk.NORMAL)
            self.download_button.bg = self.button_bg
            self.download_button.draw_button(self.button_bg)
    
    def download_task(self, url, download_type, quality, format_type, include_subs, output_path):
        try:
            output_path = Path(output_path)
            if not output_path.exists():
                output_path.mkdir(parents=True)
                logger.info(f"Created output directory: {output_path}")
            
            # Configure format based on quality and format type
            video_format = self.get_format_for_quality(quality, format_type)
            
            # Configure yt-dlp options with optimized settings
            ydl_opts = {
                'format': video_format,
                'outtmpl': str(output_path / '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
                'writesubtitles': include_subs,
                'writeautomaticsub': include_subs,
                'subtitleslangs': ['en'],
                'fragment_retries': 5,  # Increase retries
                'retries': 5,  # Increase retries
                'file_access_retries': 5,  # Increase retries
                'extractor_retries': 5,  # Increase retries
                'socket_timeout': 20,  # Increase timeout
                'buffersize': 1024 * 1024 * 4,  # Larger buffer size
                'http_chunk_size': 1048576 * 4,  # Larger chunk size
                'concurrent_fragment_downloads': 8,  # More concurrent downloads
                'verbose': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
                'postprocessor_args': {
                    'ffmpeg': ['-threads', '8']  # Use more threads for processing
                }
            }
            
            # Add audio-only options if needed
            if format_type == "audio":
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            
            if download_type == "single":
                self.download_single_video(url, ydl_opts)
            else:
                self.download_playlist(url, ydl_opts)
                
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            logger.error(error_msg)
            self.update_status(error_msg)
    
    def get_format_for_quality(self, quality, format_type):
        """Determine the yt-dlp format string based on selected quality and type"""
        if format_type == "audio":
            # Get best audio, preferably mp3 if available, or best overall audio
            # Use a fallback to 'bestaudio' if mp3 is not directly available
            return 'bestaudio[ext=mp3]/bestaudio'
            
        # For video formats, prioritize mp4 if available at the specified height
        preferred_format = 'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]'.format(quality=quality.replace('p', ''))
        
        # Fallback to best overall video+audio stream if preferred formats are not available
        fallback_format = 'best'
        
        # Combine preferred and fallback formats
        return f'{preferred_format}/{fallback_format}'
    
    def progress_hook(self, d):
        if not self.is_downloading:
            raise Exception("Download cancelled by user")
            
        if d['status'] == 'downloading':
            try:
                # Get progress information
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', '--').replace(' ', '')
                eta = d.get('_eta_str', '--').replace(' ', '')
                downloaded = d.get('_downloaded_str', '--')
                total = d.get('_total_bytes_str', '--')
                
                # Update progress bar
                if percent.endswith('%'):
                    progress = float(percent[:-1])
                    self.progress_bar.set_progress(progress)
                    self.percent_var.set(f"{int(progress)}%")
                
                # Update speed and ETA
                self.speed_var.set(f"Speed: {speed}")
                self.eta_var.set(f"ETA: {eta}")
                
                # Create a detailed progress message
                progress_msg = f"⬇️ Downloading... {percent}\n"
                progress_msg += f"📊 Progress: {downloaded} of {total}\n"
                progress_msg += f"⚡ Speed: {speed}\n"
                progress_msg += f"⏱️ ETA: {eta}\n"
                
                # Update log with formatted message
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, progress_msg)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                
            except Exception as e:
                logger.error(f"Error updating progress: {str(e)}")
                
        elif d['status'] == 'finished':
            filename = d.get('filename', '').split('/')[-1]
            # Use Windows-style path separator if on Windows
            if os.name == 'nt':
                filename = d.get('filename', '').split('\\')[-1]
            
            complete_msg = f"✅ Download complete!\n"
            complete_msg += f"📁 Saved as: {filename}\n"
            complete_msg += f"📍 Location: {os.path.dirname(d.get('filename', ''))}"
            
            self.update_status(complete_msg)
            self.update_progress(100)
            
            # Add to download history
            self.download_history.append({
                'title': self.current_video_info.get('title', 'Unknown') if hasattr(self, 'current_video_info') else 'Unknown',
                'filename': filename,
                'filepath': d.get('filename', ''),
                'format': self.format_var.get(),
                'type': self.format_var.get(),  # Changed from self.type_var.get() to self.format_var.get()
                'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            
            # Update download history display
            self.update_download_history()
            
            logger.info(f"Download complete: {filename}")
        
        elif d['status'] == 'error':
            error_msg = d.get('error', 'Unknown error occurred')
            
            # Clean up error message
            import re
            error_msg = re.sub(r'\x1b\[[0-9;]*m', '', error_msg)
            error_msg = re.sub(r'See\s+https?://[^\s]+', '', error_msg)
            error_msg = re.sub(r'Also see\s+https?://[^\s]+', '', error_msg)
            error_msg = error_msg.replace("ERROR:", "").strip()
            
            # Provide user-friendly error message for private videos
            if "Private video" in error_msg:
                if self.cookies_var.get():
                    error_msg = "This is a private video. The provided authentication cookies don't have access to this video."
                else:
                    error_msg = "This is a private video that requires authentication. Enable the 'Use Authentication Cookies' option to download private videos."
            
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, f"❌ Error: {error_msg}")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
    
    def download_single_video(self, url, ydl_opts):
        try:
            self.update_status("🔍 Fetching video information...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.current_video_info = info  # Store for history
                title = info.get('title', 'Unknown Video')
                
                # Show video info in log
                video_info = f"📽️ Video: {title}\n"
                video_info += f"Duration: {info.get('duration_string', '--')}\n"
                video_info += f"Quality: {info.get('format_note', '--')}\n"
                video_info += "Starting download..."
                
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, video_info)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                
                logger.info(f"Downloading: {title}")
                
                # Download the video
                ydl.download([url])
                
                # Get the downloaded file path
                outfile = None
                for key in ['requested_downloads', '_download_retcode']:
                    if hasattr(ydl, key) and key == 'requested_downloads' and ydl.requested_downloads:
                        outfile = ydl.requested_downloads[0].get('filepath')
                        break
                
                # Set file's timestamp to match the video upload date
                if outfile and os.path.exists(outfile):
                    try:
                        # Try to get the upload date from the video info
                        if info.get('upload_date'):
                            # Parse the upload date (YYYYMMDD format)
                            upload_date = info.get('upload_date')
                            if upload_date and len(upload_date) == 8:
                                year = int(upload_date[0:4])
                                month = int(upload_date[4:6])
                                day = int(upload_date[6:8])
                                
                                # Create a timestamp
                                date_time = datetime.datetime(year, month, day, 12, 0, 0)
                                timestamp = date_time.timestamp()
                                
                                # Set the file's access and modification times
                                os.utime(outfile, (timestamp, timestamp))
                                logger.info(f"Set file timestamp to video upload date: {year}-{month}-{day}")
                                
                                # Add this info to the completion message
                                self.update_status(f"✅ Download complete! Set file date to original upload date: {year}-{month}-{day}")
                    except Exception as e:
                        logger.error(f"Failed to set file timestamp: {str(e)}")
        except Exception as e:
            error_msg = str(e)
            # Check for private video error and provide a more user-friendly message
            if "Private video" in error_msg:
                if self.cookies_var.get():
                    error_msg = "❌ Error: This is a private video. The provided authentication cookies don't have access to this video."
                else:
                    error_msg = "❌ Error: This is a private video that requires authentication. Enable the 'Use Authentication Cookies' option to download private videos."
            else:
                error_msg = f"❌ Error downloading video:\n{error_msg}"
            
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, error_msg)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            logger.error(f"Error downloading video: {str(e)}")
            raise
    
    def download_playlist(self, url, ydl_opts):
        try:
            # If we already have playlist info, use it
            if self.current_playlist_info and 'entries' in self.current_playlist_info:
                playlist_info = self.current_playlist_info
                videos = self.current_playlist_videos  # Use our filtered videos list
            else:
                # First get playlist info
                extract_info_opts = ydl_opts.copy()
                extract_info_opts['extract_flat'] = True
                
                self.update_status("Fetching playlist information...")
                with yt_dlp.YoutubeDL(extract_info_opts) as ydl:
                    playlist_info = ydl.extract_info(url, download=False)
                    
                    # Create video cards if not already done
                    if 'entries' in playlist_info and not self.current_playlist_info:
                        # Filter entries to remove private videos
                        filtered_entries = []
                        for entry in playlist_info['entries']:
                            if entry is not None:
                                filtered_entries.append(entry)
                        
                        videos = filtered_entries
                        self.current_playlist_info = playlist_info
                        self.current_playlist_videos = filtered_entries
                        
                        # Update playlist info text
                        playlist_title = playlist_info.get('title', 'Unknown Playlist')
                        video_count = len(filtered_entries)
                        self.playlist_info_var.set(f"{video_count} videos • {playlist_title}")
                        
                        # Clear and add video cards
                        self.playlist_view.clear()
                        for i, entry in enumerate(filtered_entries):
                            self.playlist_view.add_video(entry, i)
            
            if self.current_playlist_videos:
                videos = self.current_playlist_videos
                total_videos = len(videos)
                playlist_title = playlist_info.get('title', 'Unknown Playlist')
                
                logger.info(f"Found {total_videos} videos in playlist: {playlist_title}")
                self.update_status(f"Starting parallel download of {total_videos} videos...")
                
                # Create a thread pool - limit to max 3 concurrent downloads to avoid rate limiting
                max_workers = min(3, total_videos)
                self.download_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
                futures = []
                
                # Track completed downloads to update progress
                self.completed_videos = 0
                self.total_videos = total_videos
                self.failed_videos = 0
                
                # Submit each video to the thread pool
                for i, video in enumerate(videos):
                    if video is None:
                        continue
                        
                    # Get proper video URL - this is critical for playlist items
                    video_url = None
                    
                    # Try different ways to get the video URL
                    if 'url' in video:
                        video_url = video['url']
                    elif 'id' in video:
                        # Construct URL from ID
                        video_url = f"https://www.youtube.com/watch?v={video['id']}"
                    elif 'webpage_url' in video:
                        video_url = video['webpage_url']
                    
                    if not video_url:
                        logger.warning(f"Could not find URL for video {i+1} in playlist")
                        continue
                    
                    # Log the URL we're using
                    logger.info(f"Using URL for video {i+1}: {video_url}")
                    
                    # Update card status to queued
                    self.playlist_view.update_video_progress(i, 0, "pending")
                    
                    # Configure download options for this video
                    video_opts = ydl_opts.copy()
                    video_opts['extract_flat'] = False
                    
                    # Create a progress hook for this specific video
                    def create_progress_hook(video_index):
                        def video_progress_hook(d):
                            if not self.is_downloading:
                                raise Exception("Download cancelled by user")
                                
                            if d['status'] == 'downloading':
                                try:
                                    percent = d.get('_percent_str', '0%').strip()
                                    if percent.endswith('%'):
                                        percent = float(percent[:-1])
                                        self.playlist_view.update_video_progress(video_index, percent, "downloading")
                                except Exception:
                                    pass
                            elif d['status'] == 'finished':
                                self.playlist_view.update_video_progress(video_index, 100, "completed")
                                with self.progress_lock:
                                    self.completed_videos += 1
                                    # Update overall progress based on completed video count
                                    overall_progress = int((self.completed_videos / self.total_videos) * 100)
                                    self.update_progress(overall_progress)
                            elif d['status'] == 'error':
                                with self.progress_lock:
                                    self.failed_videos += 1
                                    self.completed_videos += 1
                                    # Update overall progress
                                    overall_progress = int((self.completed_videos / self.total_videos) * 100)
                                    self.update_progress(overall_progress)
                        return video_progress_hook
                    
                    # Add video-specific progress hook
                    video_opts['progress_hooks'] = [create_progress_hook(i)]
                    
                    # Make sure we include cookies for private videos if available
                    if self.cookies_var.get() and self.has_cookies:
                        video_opts['cookiefile'] = str(self.cookies_file)
                    
                    # Submit this video download to the thread pool
                    future = self.download_pool.submit(self.download_single_video_task, video_url, video_opts, i)
                    futures.append(future)
                
                # Create a cancellation check thread
                def monitor_downloads():
                    """Monitor the progress of all downloads in the playlist"""
                    try:
                        while self.is_downloading and any(not f.done() for f in futures):
                            time.sleep(0.5)  # Check every half second
                            
                            # Check for any failed downloads
                            failed_count = sum(1 for f in futures if f.done() and not f.result())
                            if failed_count > 0:
                                self.update_status(f"⚠️ {failed_count} videos failed to download. Continuing with remaining videos...")
                        
                        # If we've reached here, either downloads are done or user cancelled
                        if not self.is_downloading:
                            # Cancel any pending futures
                            for f in futures:
                                if not f.done():
                                    f.cancel()
                            
                            self.download_pool.shutdown(wait=False)
                            self.update_status("Downloads cancelled")
                        else:
                            # All downloads completed
                            successful = self.completed_videos - self.failed_videos
                            total = self.total_videos
                            
                            # Calculate success rate
                            success_rate = (successful / total) * 100 if total > 0 else 0
                            
                            # Update final status
                            if self.failed_videos > 0:
                                self.update_status(f"Playlist download complete: {successful}/{total} videos downloaded successfully ({success_rate:.1f}% success rate)")
                                self.update_status(f"Failed downloads: {self.failed_videos} videos")
                            else:
                                self.update_status(f"✅ Playlist download complete: All {total} videos downloaded successfully")
                            
                            # Log final statistics
                            logger.info(f"Playlist download completed. Success rate: {success_rate:.1f}%")
                            logger.info(f"Successful downloads: {successful}")
                            logger.info(f"Failed downloads: {self.failed_videos}")
                        
                        # Ensure progress is at 100%
                        self.update_progress(100)
                        
                        # Shutdown the thread pool
                        self.download_pool.shutdown(wait=True)
                        
                        # Re-enable the download button
                        self.download_button.config(state=tk.NORMAL)
                        self.download_button.bg = self.button_bg
                        self.download_button.draw_button(self.button_bg)
                        
                    except Exception as e:
                        logger.error(f"Error in download monitoring: {str(e)}")
                        self.update_status(f"❌ Error monitoring downloads: {str(e)}")
                        # Still try to clean up
                        try:
                            self.download_pool.shutdown(wait=False)
                            self.download_button.config(state=tk.NORMAL)
                        except:
                            pass
                
                # Start the monitoring thread
                monitor_thread = threading.Thread(target=monitor_downloads, daemon=True)
                monitor_thread.start()
            else:
                raise Exception("No available videos found in playlist")
        except Exception as e:
            logger.error(f"Error downloading playlist: {str(e)}")
            self.update_status(f"Error: {str(e)}")
            # Re-enable the download button
            self.download_button.config(state=tk.NORMAL)
            self.download_button.bg = self.button_bg
            self.download_button.draw_button(self.button_bg)
            raise
    
    def download_single_video_task(self, url, ydl_opts, index):
        """Individual download task for a single video in a playlist (runs in a thread)"""
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                # Ensure we have a valid URL
                if not url:
                    logger.error(f"No valid URL for video {index+1}")
                    self.playlist_view.update_video_progress(index, 0, "error")
                    self.playlist_view.video_cards[index].status_var.set("❌ Missing URL")
                    with self.progress_lock:
                        self.failed_videos += 1
                        self.completed_videos += 1
                        overall_progress = int((self.completed_videos / self.total_videos) * 100)
                        self.update_progress(overall_progress)
                    return False
                    
                # Update status in UI
                self.playlist_view.update_video_progress(index, 0, "downloading")
                
                # Log what we're downloading
                logger.info(f"Starting download for video {index+1}: {url}")
                
                # Perform the download
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        # Check if the video information can be accessed first
                        info = ydl.extract_info(url, download=False)
                        
                        # If we got here, we can access the video, so download it
                        if info:
                            logger.info(f"Downloading video: {info.get('title', 'Unknown')}")
                            self.playlist_view.video_cards[index].status_var.set(f"⬇️ Downloading...")
                            
                            # Now actually download the video
                            ydl.download([url])
                            
                            # Update UI for completion
                            logger.info(f"Video {index+1} download completed")
                            self.playlist_view.update_video_progress(index, 100, "completed")
                            
                            with self.progress_lock:
                                self.completed_videos += 1
                                overall_progress = int((self.completed_videos / self.total_videos) * 100)
                                self.update_progress(overall_progress)
                            return True
                        else:
                            # Could not get video info
                            raise Exception("Could not extract video information")
                            
                    except Exception as e:
                        error_msg = str(e)
                        # Clean up error message and handle private videos gracefully
                        if "Private video" in error_msg:
                            clean_msg = "Private video"
                            if self.cookies_var.get():
                                clean_msg = "Private video (no access with current cookies)"
                            self.playlist_view.video_cards[index].status_var.set(f"⛔ {clean_msg}")
                        else:
                            # Format other errors
                            import re
                            clean_error = re.sub(r'\x1b\[[0-9;]*m', '', error_msg)
                            clean_error = re.sub(r'ERROR:', '', clean_error).strip()
                            if len(clean_error) > 50:
                                clean_error = clean_error[:47] + "..."
                            self.playlist_view.video_cards[index].status_var.set(f"❌ {clean_error}")
                        
                        logger.error(f"Error downloading video {index+1}: {error_msg}")
                        self.playlist_view.update_video_progress(index, 0, "error")
                        
                        # Don't raise the exception - this allows other downloads to continue
                        with self.progress_lock:
                            self.failed_videos += 1
                            self.completed_videos += 1
                            overall_progress = int((self.completed_videos / self.total_videos) * 100)
                            self.update_progress(overall_progress)
                        return False
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1} failed for video {index+1}. Retrying in {retry_delay} seconds...")
                    self.playlist_view.video_cards[index].status_var.set(f"⚠️ Retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Error downloading video {index+1} after {max_retries} attempts: {str(e)}")
                    self.playlist_view.update_video_progress(index, 0, "error")
                    
                    # Always update progress counters even if the download failed
                    with self.progress_lock:
                        self.failed_videos += 1
                        self.completed_videos += 1
                        overall_progress = int((self.completed_videos / self.total_videos) * 100)
                        self.update_progress(overall_progress)
                    return False
    
    def fetch_playlist_info(self, url):
        """Fetch playlist information without downloading"""
        try:
            self.update_status("🔍 Fetching playlist information...")
            self.download_button.config(state=tk.DISABLED)
            
            # Configure options just for extracting playlist info
            extract_opts = {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'forcejson': True,
            }
            
            # Add cookies for private playlists if available
            # if self.cookies_var.get() and self.has_cookies:
            #     extract_opts['cookiefile'] = str(self.cookies_file)
            #     self.update_status("Using cookies for authentication...")
            
            with yt_dlp.YoutubeDL(extract_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if 'entries' in info and info['entries']:
                    # Filter out private videos if option is enabled
                    filtered_entries = []
                    skipped_count = 0
                    
                    for entry in info['entries']:
                        if entry is None:
                            continue
                            
                        # Skip private videos (we'll check this when we get detailed info)
                        filtered_entries.append(entry)
                    
                    # Update with filtered entries
                    info['entries'] = filtered_entries
                    self.current_playlist_info = info
                    self.current_playlist_videos = filtered_entries
                    
                    # Update playlist info text
                    playlist_title = info.get('title', 'Unknown Playlist')
                    video_count = len(filtered_entries)
                    self.playlist_info_var.set(f"{video_count} videos • {playlist_title}")
                    
                    # Clear existing video cards
                    self.playlist_view.clear()
                    
                    # Fetch detailed info for each video
                    self.update_status(f"🔍 Found {video_count} videos in playlist: {playlist_title}")
                    
                    # Add video cards for each entry
                    available_videos = []
                    for i, entry in enumerate(filtered_entries):
                        # Try to get more info about the video
                        try:
                            # Get proper video URL - this is critical for playlist items
                            video_url = None
                            
                            # Try different ways to get the video URL
                            if 'url' in entry:
                                video_url = entry['url']
                            elif 'id' in entry:
                                # Construct URL from ID
                                video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                            elif 'webpage_url' in entry:
                                video_url = entry['webpage_url']
                                
                            if not video_url:
                                logger.warning(f"Could not find URL for video {i+1} in playlist")
                                continue
                                
                            logger.info(f"Fetching info for video {i+1}: {video_url}")
                            
                            # Only extract some basic info to avoid too many API calls
                            with yt_dlp.YoutubeDL({'skip_download': True, 'quiet': True}) as video_ydl:
                                try:
                                    video_info = video_ydl.extract_info(video_url, download=False, process=False)
                                    
                                    # Ensure the video has a URL
                                    if not video_info.get('url') and not video_info.get('webpage_url') and video_url:
                                        # Add the URL to the video info
                                        video_info['url'] = video_url
                                    
                                    # Check if this is a private video
                                    if video_info:
                                        available_videos.append(video_info)
                                        self.playlist_view.add_video(video_info, len(available_videos)-1)
                                    else:
                                        skipped_count += 1
                                except Exception as e:
                                    error_str = str(e)
                                    if "Private video" in error_str:
                                        skipped_count += 1
                                        logger.info(f"Skipped private video: {video_url}")
                                    else:
                                        # For other errors, still add the video with basic info
                                        # Add the URL to ensure we can download it
                                        entry['url'] = video_url
                                        available_videos.append(entry)
                                        self.playlist_view.add_video(entry, len(available_videos)-1)
                        except Exception as e:
                            # Use basic info if detailed extraction fails
                            if "Private video" not in str(e):
                                # Make sure we have a valid URL
                                if 'url' not in entry and 'id' in entry:
                                    entry['url'] = f"https://www.youtube.com/watch?v={entry['id']}"
                                    
                                available_videos.append(entry)
                                self.playlist_view.add_video(entry, len(available_videos)-1)
                                logger.warning(f"Could not get detailed info for video {i+1}: {str(e)}")
                            else:
                                skipped_count += 1
                                logger.info(f"Skipped private video at position {i+1}")
                    
                    # Update current playlist info with available videos
                    self.current_playlist_videos = available_videos
                    
                    # Update status with skip info
                    if skipped_count > 0:
                        self.update_status(f"✅ Playlist information loaded: {playlist_title} ({skipped_count} private videos skipped)")
                    else:
                        self.update_status(f"✅ Playlist information loaded: {playlist_title}")
                        
                    # Start download automatically only if we have videos to download
                    if available_videos:
                        # Get selected options
                        quality = self.quality_var.get()
                        format_type = self.format_var.get()
                        include_subs = self.subtitle_var.get()
                        output_dir = self.save_location
                        
                        # Update UI state
                        self.is_downloading = True
                        
                        # Start download in a separate thread
                        self.download_thread = threading.Thread(
                            target=self.download_task,
                            args=(url, "playlist", quality, format_type, include_subs, output_dir)
                        )
                        self.download_thread.daemon = True
                        self.download_thread.start()
                        
                        # Start progress monitoring
                        self.root.after(100, self.check_download_progress)
                    else:
                        self.update_status("No videos available to download in this playlist")
                        self.download_button.config(state=tk.NORMAL)
                else:
                    self.update_status("❌ No videos found in playlist")
                    messagebox.showerror("Error", "No videos found in playlist")
                    self.download_button.config(state=tk.NORMAL)
            
        except Exception as e:
            logger.error(f"Error fetching playlist info: {str(e)}")
            self.update_status(f"❌ Error fetching playlist info: {str(e)}")
            messagebox.showerror("Error", f"Could not fetch playlist information:\n{str(e)}")
            self.download_button.config(state=tk.NORMAL)
    
    def playlist_toggle(self, event=None):
        """Show or hide the playlist view based on the playlist switch"""
        if self.playlist_var.get():
            # Show playlist view and update UI
            self.playlist_view_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        else:
            # Hide playlist view
            self.playlist_view_frame.pack_forget()
            
            # Clear playlist info
            self.current_playlist_info = None
            self.current_playlist_videos = []
            self.current_video_index = -1
            self.playlist_view.clear()

    def search_videos(self):
        """Search for videos without downloading"""
        url = self.url_entry.get().strip()
        if url == "Paste YouTube URL here..." or not url:
            messagebox.showerror("Error", "Please enter a YouTube URL")
            return
        
        # Show the playlist view section regardless of playlist checkbox
        self.playlist_view_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        
        # Start search in a thread
        threading.Thread(target=self.fetch_video_info, args=(url,), daemon=True).start()

    def fetch_video_info(self, url):
        """Fetch video information for display without downloading"""
        try:
            self.search_button.config(state=tk.DISABLED)
            self.update_status("🔍 Searching for videos...")
            
            # Configure options for video info extraction
            extract_opts = {
                'extract_flat': False,  # Get detailed info for single videos
                'skip_download': True,
                'quiet': True,
                'no_warnings': True,
                'forcejson': True,
            }
            
            # If authentication cookies are enabled, use them
            # if self.cookies_var.get() and self.has_cookies:
            #     extract_opts['cookiefile'] = str(self.cookies_file)
            #     logger.info(f"Using cookies file for search: {self.cookies_file}")
            
            with yt_dlp.YoutubeDL(extract_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Clear the playlist view
                self.playlist_view.clear()
                
                if info.get('_type') == 'playlist':
                    # It's a playlist
                    playlist_title = info.get('title', 'Unknown Playlist')
                    entries = info.get('entries', [])
                    
                    # Filter out None entries
                    entries = [e for e in entries if e is not None]
                    
                    # Update playlist info
                    self.current_playlist_info = info
                    self.current_playlist_videos = entries
                    
                    # Enable playlist mode automatically
                    self.playlist_var.set(True)
                    
                    # Update playlist info text
                    video_count = len(entries)
                    self.playlist_info_var.set(f"{video_count} videos • {playlist_title}")
                    
                    # Add video cards for each entry
                    for i, entry in enumerate(entries):
                        self.playlist_view.add_video(entry, i)
                    
                    self.update_status(f"✅ Found playlist: {playlist_title} with {video_count} videos")
                    
                    # Update description panel with all videos metadata
                    # self.description_panel.update_description(entries)
                else:
                    # It's a single video
                    self.current_playlist_info = None
                    
                    # Create a special playlist view with just this video
                    self.playlist_info_var.set("Single Video")
                    self.playlist_view.add_video(info, 0)
                    
                    # Store as a single item list
                    self.current_playlist_videos = [info]
                    
                    self.update_status(f"✅ Found video: {info.get('title', 'Unknown Video')}")
                    
                    # Update description panel with single video metadata
                    self.description_panel.update_description(info)
            
            self.search_button.config(state=tk.NORMAL)
        except Exception as e:
            logger.error(f"Error searching for videos: {str(e)}")
            self.update_status(f"❌ Error searching for videos: {str(e)}")
            messagebox.showerror("Error", f"Could not fetch video information:\n{str(e)}")
            self.search_button.config(state=tk.NORMAL)

    def update_download_history(self):
        """Update the download history display"""
        if not hasattr(self, 'download_history_frame'):
            return
            
        # Clear current history display
        for widget in self.download_history_frame.winfo_children():
            widget.destroy()
            
        # Show recent downloads (last 5)
        recent = self.download_history[-5:] if self.download_history else []
        
        if not recent:
            no_history = ttk.Label(self.download_history_frame, 
                                text="No recent downloads", 
                                font=self.normal_font)
            no_history.pack(pady=10)
            return
            
        # Add each download as a compact entry
        for i, download in enumerate(reversed(recent)):
            entry_frame = ttk.Frame(self.download_history_frame, style="Card.TFrame")
            entry_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
            
            # Title with emoji indicating type
            emoji = "🎵" if download['type'] == "audio" else "🎬"
            title_text = f"{emoji} {download['title'][:40]}{'...' if len(download['title']) > 40 else ''}"
            title = ttk.Label(entry_frame, text=title_text, font=("Inter", 10, "bold"))
            title.pack(anchor=tk.W, pady=(5, 2))
            
            # Format and time
            details = ttk.Label(entry_frame, 
                            text=f"{download['format']} • {download['time']}", 
                            font=self.small_font)
            details.pack(anchor=tk.W, pady=(0, 2))
            
            # Filename (truncated) with open button
            file_frame = ttk.Frame(entry_frame)
            file_frame.pack(fill=tk.X, pady=(0, 5))
            
            file_path = download['filepath']
            dir_path = os.path.dirname(file_path)
            
            file_label = ttk.Label(file_frame, 
                               text=f"📁 {download['filename'][:30]}{'...' if len(download['filename']) > 30 else ''}", 
                               font=self.small_font)
            file_label.pack(side=tk.LEFT)
            
            # Open folder button
            def create_open_callback(path):
                return lambda: self.open_folder(path)
                
            open_btn = ttk.Button(file_frame, 
                              text="Open Folder", 
                              command=create_open_callback(dir_path),
                              style="Small.TButton",
                              width=10)
            open_btn.pack(side=tk.RIGHT)
            
            # Add separator except for last item
            if i < len(recent) - 1:
                separator = ttk.Separator(self.download_history_frame, orient="horizontal")
                separator.pack(fill=tk.X, pady=5, padx=5)
    
    def open_folder(self, path):
        """Open the folder containing the downloaded file"""
        try:
            if os.path.exists(path):
                # Open folder with default file explorer
                if os.name == 'nt':  # Windows
                    os.startfile(path)
                elif os.name == 'posix':  # macOS and Linux
                    import subprocess
                    if sys.platform == 'darwin':  # macOS
                        subprocess.Popen(['open', path])
                    else:  # Linux
                        subprocess.Popen(['xdg-open', path])
            else:
                logger.error(f"Path does not exist: {path}")
                self.update_status(f"❌ Folder not found: {path}")
        except Exception as e:
            logger.error(f"Error opening folder: {str(e)}")
            self.update_status(f"❌ Error opening folder: {str(e)}")

    def clear_logs(self):
        """Clear the log display"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, "Download logs will appear here...\n")
        self.log_text.config(state=tk.DISABLED)
        try:
            logger.info("Logs cleared")
        except Exception:
            pass  # Ignore any logging errors

if __name__ == "__main__":
    root = tk.Tk()
    app = DownloaderApp(root)
    root.mainloop() 