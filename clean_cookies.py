import os

input_file = "D:\\Fluxbase\\Yt Download model\\yt-backend\\youtube.com_cookies.txt"
output_file = "D:\\Fluxbase\\Yt Download model\\yt-backend\\clean_cookies.txt"

print("Cleaning YouTube Cookies...")

try:
    with open(input_file, 'r', encoding='utf-8') as f_in, open(output_file, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            # Keep comments/header lines
            if line.startswith('#'):
                f_out.write(line)
                continue
                
            # Only keep cookies that belong to youtube domains
            parts = line.strip().split('\t')
            if len(parts) >= 1:
                domain = parts[0].strip().lower()
                if '.youtube.com' in domain or 'youtube.com' == domain:
                    f_out.write(line)
                    
    print(f"Successfully cleaned cookies!")
    
    # Replace old file with new clean file
    os.remove(input_file)
    os.rename(output_file, input_file)
    print("Cookie replacement complete. Ready for GitHub Push!")

except Exception as e:
    print(f"Error filtering cookies: {e}")
