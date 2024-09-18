CSS_STYLE = """
.canvas {
    # width: 100% !important;
    # max-width: 100% !important;
    width: 100vh;
}

.fullheight {
    height: 80vh;
}

.chatbot {
    flex-grow: 1;
    overflow: auto;
    position: relative;
    z-index: 100;
}

.bottom-bar {
    position: fixed;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    width: 80vh;
    z-index: 1000;
}

.unicode-circle {
  font-family: 'Arial Unicode MS', Arial, sans-serif;
  font-size: 14px;
  border-radius: 50%;
  border: 1px solid black;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  display: inline-block;
  background-color: white;
}

.circle-link {
  font-family: 'Arial Unicode MS', Arial, sans-serif;
  text-decoration: none;
  color: black;
  border-radius: 50%;
  border: 1px solid black;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  display: inline-block;
  background-color: white;
  cursor: pointer;
}

.circle-link:hover {
  background-color: #e0e0e0;
}

.circle-link:hover::after {
  content: attr(title);
  position: absolute;
  white-space: nowrap;
}
"""
