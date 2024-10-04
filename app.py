import streamlit as st
from openai import OpenAI
from openai import AzureOpenAI
import json
import uuid
import re
import itertools
from typing import Dict, List, Optional, Union
from datetime import datetime
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from googletrends import get_google_trends
from news import get_news
from get_reddit_headlines import get_reddit_headlines

__name__ = "RogueGPT"
__version__ = "0.9.2"
__author__ = "Alexander Loth"
__email__ = "Alexander.Loth@microsoft.com"
__report_a_bug__ = "https://github.com/aloth/RogueGPT/issues"

# Constants
CONFIG_FILE = 'prompt_engine.json'

def generate_fragment(prompt: str, base_url: str, api_key: str, api_type: str, api_version: str = None, model: str = None) -> str:
    """
    Generates a news fragment using OpenAI's or Azure OpenAI's GPT model and returns the generated response.

    Args:
        prompt (str): The prompt to generate the news fragment.
        base_url (str): The base URL for the OpenAI or Azure OpenAI API.
        api_key (str): The API key for authentication.
        api_type (str): Specifies the type of API, either 'OpenAI' or 'AzureOpenAI'.
        api_version (str, optional): The API version (only needed for Azure OpenAI). Defaults to None.
        model (str, optional): The model identifier for the GPT model (e.g., 'gpt-4'). Defaults to None.

    Returns:
        str: The generated response from the model.

    Raises:
        ValueError: If an invalid API type is provided.
    """

    # Initialize the client based on the API type (OpenAI or AzureOpenAI)
    if api_type == "OpenAI":
        client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
    elif api_type == "AzureOpenAI":
        client = AzureOpenAI(
            api_key=api_key,  
            api_version=api_version,
            azure_endpoint=base_url
        )
    else:
        raise ValueError("Invalid API type. Must be either 'OpenAI' or 'AzureOpenAI'.")

    # Create a streaming completion request with the provided prompt and model
    stream = client.chat.completions.create(
        model = model,
        messages = [{"role": "user", "content": prompt}],
        stream = True
    )

    # Process and return the streamed response
    generated_response = st.write_stream(stream)

    return generated_response

def save_fragment(fragment: dict) -> None:
    """
    Saves a news fragment to the MongoDB database.
    
    Args:
        fragment (dict): The news fragment to be saved.

    Raises:
        Exception: If there's an error while saving the fragment to the database.
    """
    try:
        with MongoClient(st.secrets["mongo"]["connection"], server_api=ServerApi('1')) as client:
            db = client.realorfake
            collection = db.fragments
            collection.insert_one(fragment)
        st.success("Fragment saved successfully.")
    except Exception as e:
        st.error(f"Error saving fragment: {str(e)}")

def render_ui(component_dict: dict, key_prefix: str = "") -> dict:
    """
    Dynamically renders UI components based on the configuration provided in the components dictionary.

    Args:
        component_dict (dict): A dictionary containing the UI components configuration.
        key_prefix (str): A prefix added to the keys to ensure uniqueness (useful in recursion).

    Returns:
        dict: A dictionary of user selections for each component.
    """
    user_selections = {}
    for key, value in component_dict.items():
        if isinstance(value, dict):  # If the value is a nested dict, use a selectbox for top-level selection
            selected_option = st.selectbox(f'Choose {key}', list(value.keys()), key=key_prefix+f'selectbox-{key}')
            user_selections[key] = selected_option
            # Based on the selected option, render the nested component (e.g., Styles)
            nested_dict = value[selected_option]
            for nested_key, nested_value in nested_dict.items():
                if isinstance(nested_value, list):  # Render multiselect for nested lists
                    selected_nested_options = st.multiselect(f'Choose {nested_key}', nested_value, default=nested_value, key=key_prefix+f'multiselect-{key}-{nested_key}')
                    user_selections[f"{nested_key}"] = selected_nested_options
        elif isinstance(value, list):  # For top-level lists, use multiselect
            selected_options = st.multiselect(f'Choose {key}', value, default=value, key=key_prefix+f'multiselect-{key}')
            user_selections[key] = selected_options
    return user_selections
    
def collect_keys(component_dict: dict, collected_keys: list = []) -> list:
    """
    Recursively collects all keys from nested dictionaries.

    Args:
        component_dict (dict): The dictionary to collect keys from.
        collected_keys (list, optional): A list to store collected keys. Defaults to an empty list.

    Returns:
        list: A list of all collected keys.
    """
    for key, value in component_dict.items():
        collected_keys.append(key)
        if isinstance(value, dict):
            for sub_key in value.keys():
                collect_keys(value[sub_key], collected_keys)
    return collected_keys

def fix_structure(selections: dict) -> dict:
    """
    Ensures all selections are in list form.

    Args:
        selections (dict): A dictionary of user selections.

    Returns:
        dict: A dictionary with all values converted to lists.
    """
    corrected_selections = {}
    for key, value in selections.items():
        if isinstance(value, list):  # If the value is already a list, use it as is
            corrected_selections[key] = value
        else:  # Treat single strings as a list with a single element
            corrected_selections[key] = [value]
    return corrected_selections

def manual_data_entry_ui() -> None:
    """
    Renders UI for manual data entry of news fragments.

    This function doesn't return anything but updates the Streamlit UI.
    """
    fragment_id = uuid.uuid4().hex
    st.header("Input News Details")

    # Automatically generated FragmentID (display only, no input from user)
    st.text_input("Fragment ID", value=fragment_id, disabled=True)

    # Other details with user input
    content = st.text_area("Content")
    origin = st.selectbox("Origin", ["Human", "Machine"])
    if origin == "Human":
        human_outlet = st.text_input("Publishing Outlet Name")
        human_url = st.text_input("URL of News Source")
        machine_model = ""
        machine_prompt = ""
    else:
        human_outlet = ""
        human_url = ""
        machine_model = st.text_input("Generative AI Model")
        machine_prompt = st.text_area("Prompt")

    language = st.selectbox("Language", ["en", "de", "fr", "es"])
    is_fake = st.checkbox("Is this fake news?")
    creation_date = datetime.today()

    # Button to submit and save the input data
    submit_button = st.button("Submit")

    if submit_button:
        # Process the submitted data (for demonstration, just display it)
        st.write(f"Fragment ID: {fragment_id}")
        st.write(f"Content: {content}")
        st.write(f"Origin: {origin}")
        st.write(f"Publishing Outlet Name: {human_outlet}")
        st.write(f"URL of News Source: {human_url}")
        st.write(f"Generative AI Model: {machine_model}")
        st.write(f"Prompt: {machine_prompt}")
        st.write(f"Language: {language}")
        st.write(f"Is Fake: {is_fake}")
        st.write(f"Creation Date: {creation_date}")

        fragment = {
            "FragmentID": fragment_id,
            "Content": content,
            "Origin": origin,
            "HumanOutlet": human_outlet,
            "HumanURL": human_url,
            "MachineModel": machine_model,
            "MachinePrompt": machine_prompt,
            "ISOLanguage": language,
            "IsFake": is_fake,
            "CreationDate": creation_date
        }
        
        save_fragment(fragment)
        st.rerun()

def automatic_news_generation_ui() -> None:
    """
    Renders UI for automatic news generation and handles the logic for generating news fragments.

    This function doesn't return anything but updates the Streamlit UI and generates news fragments.
    """
    st.header("Automatic News Generation")

    st.subheader("Prompt")

    # Function to load JSON data
    def load_json(filename):
        with open(filename, 'r') as f:
            return json.load(f)

    # Load the JSON structure
    data = load_json(CONFIG_FILE)
    prompt_template = data["PromptTemplate"]
    generator_url = data["GeneratorURL"]
    generator_api_key = data["GeneratorAPIKey"]
    generator_api_type = data["GeneratorAPIType"]
    generator_api_version = data["GeneratorAPIVersion"]
    generator_model = data["GeneratorModel"]

    components = data["Components"]
    all_possible_keys = collect_keys(components)

    # Identifying placeholders including nested ones
    placeholders = re.findall(r"\[\[(.*?)\]\]", prompt_template)
    uncovered_placeholders = [ph for ph in placeholders if ph not in all_possible_keys]

    # User inputs for PromptTemplate, GeneratorServerURL, and GeneratorModel
    user_prompt_template = st.text_input("Prompt Template", prompt_template)

    # Render UI components based on JSON and collect selections
    user_selections = render_ui(components)

    # Find placeholders in the template that are not covered in the JSON
    for placeholder in uncovered_placeholders:
        user_input = st.text_area(f"Enter values for {placeholder} (each line is a value)", key=f"placeholder_{placeholder}")
        # Splitting by newlines to get options array
        user_input_options = user_input.split("\n")
        user_selections[placeholder] = user_input_options

    # Initialize prompt with the template
    prompt = prompt_template

    # Replace placeholders in the template with user selections
    for placeholder, selections in user_selections.items():
        placeholder_key = f"[[{placeholder}]]"
        # Use the first selection if available
        selection_text = selections[0] if isinstance(selections, list) and selections else selections  
        prompt = prompt.replace(placeholder_key, selection_text)

    # Display the generated prompt
    st.write("Prompt Preview:", prompt)

    st.subheader("Generator")

    user_generator_url = st.text_input("Generator URL", generator_url)

    user_generator_api_key = st.text_input("Generator API Key", generator_api_key)

    user_generator_api_type = st.selectbox("Generator API Type", generator_api_type)

    user_generator_api_version = st.selectbox("Generator API Version", generator_api_version)

    user_generator_model = st.selectbox("Generator Model", generator_model)

    st.subheader("Meta data")

    user_is_fakenews = st.checkbox("Mark this as fake news?")

    if st.button("Generate"):
        # Create all combinations of the selected options
        iter_selections = fix_structure(user_selections)
        st.write(iter_selections)
        keys, values = zip(*iter_selections.items())
        combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        # Generate and display prompts for each combination
        for i, combination in enumerate(combinations):
            prompt_filled = prompt_template
            for key, value in combination.items():
                prompt_filled = prompt_filled.replace(f"[[{key}]]", value)

            st.write("Using prompt: ", prompt_filled)

            generated_fragment = generate_fragment(
                prompt = prompt_filled,
                base_url = user_generator_url,
                api_key = user_generator_api_key,
                api_type = user_generator_api_type,
                api_version = user_generator_api_version,
                model = user_generator_model
            )

            combination["FragmentID"] = uuid.uuid4().hex
            combination["Content"] = generated_fragment
            combination["Origin"] = "Machine"
            combination["MachineModel"] = user_generator_model
            combination["MachinePrompt"] = prompt_filled
            combination["IsFake"] = user_is_fakenews
            combination["CreationDate"] = datetime.today()

            save_fragment(combination)

            # Add a separator for clarity between prompts
            st.markdown("---")

def get_trends(news_source) -> list:
    if "Google Trends" == news_source:
        return get_google_trends()
    elif "Reddit" == news_source:
        return get_reddit_headlines()
    return []

#def get_news(keyword, lang, source):
#    return [{"title": "Taylor swift is the new president of USA", 
#             "description": "Taylor swift is the new president of USA.",
#             "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
#             "source": "BBC"}]

def articles_to_placeholder(articles):
    return [{
        "SourceArticleTitle": article.title,
        "SourceArticleDescription": article.description,
        "SourceArticleUrl": article.url,
        #"SourceArticleSource": article.source
        } for article in articles]

def news_from_trends_ui() -> None:
    """
    Renders UI for automatic news generation and handles the logic for generating news fragments.

    This function doesn't return anything but updates the Streamlit UI and generates news fragments.
    """
    NEWS_ID_PREFIX = "automated_news"

    st.header("Automatic News recuperation")

    st.subheader("Prompt")

    # Function to load JSON data
    def load_json(filename):
        with open(filename, 'r') as f:
            return json.load(f)

    # Load the JSON structure
    data = load_json(CONFIG_FILE)
    prompt_template_seeded_based = data["PromptTemplate"]
    prompt_template_news_based = data["PromptTemplateForNewsBased"]
    generator_url = data["GeneratorURL"]
    generator_api_key = data["GeneratorAPIKey"]
    generator_api_type = data["GeneratorAPIType"]
    generator_api_version = data["GeneratorAPIVersion"]
    generator_model = data["GeneratorModel"]
    trends_source = data["TrendsSource"]
    topic_list = data["TopicList"]

    components = data["Components"]
    all_possible_keys = collect_keys(components)
    all_possible_keys += ["SeedPhrase"]
    all_possible_keys += ["SourceArticleTitle", "SourceArticleDescription", "SourceArticleUrl"]

    # Render UI components based on JSON and collect selections
    user_selections = render_ui(components, key_prefix=NEWS_ID_PREFIX)

    automated_trends = st.checkbox("Should trends be automatically recovered", key=f"{NEWS_ID_PREFIX}_automated_trends", value=True)
    if automated_trends:
        selected_trends_source = st.selectbox(f'Select the source of trends', trends_source, key=f"{NEWS_ID_PREFIX}trends_source")
        trends_list = []
    else:
        trends_list = st.multiselect(f'Choose topics', topic_list, default=topic_list, key=f"{NEWS_ID_PREFIX}_selected_topics")
    
    based_on_real_news = st.checkbox("Should the fake news be based on real news", key=f"{NEWS_ID_PREFIX}_based_on_real_news", value=True)
    if based_on_real_news:
        prompt_template = prompt_template_news_based
    else:
        # User inputs for PromptTemplate, GeneratorServerURL, and GeneratorModel
        prompt_template = prompt_template_seeded_based


    user_prompt_template = st.text_input("Prompt Template", prompt_template, key="{NEWS_ID_PREFIX}_prompt_template")

    # Identifying placeholders including nested ones
    placeholders = re.findall(r"\[\[(.*?)\]\]", user_prompt_template)
    uncovered_placeholders = [ph for ph in placeholders if ph not in all_possible_keys]

    # Find placeholders in the template that are not covered in the JSON
    for placeholder in uncovered_placeholders:
        user_input = st.text_area(f"Enter values for {placeholder} (each line is a value)", key=f"{NEWS_ID_PREFIX}_placeholder_{placeholder}")
        # Splitting by newlines to get options array
        user_input_options = user_input.split("\n")
        user_selections[placeholder] = user_input_options

    # Initialize prompt with the template
    prompt = prompt_template_news_based if based_on_real_news else prompt_template

    # Replace placeholders in the template with user selections
    for placeholder, selections in user_selections.items():
        placeholder_key = f"[[{placeholder}]]"
        # Use the first selection if available
        selection_text = selections[0] if isinstance(selections, list) and selections else selections
        if isinstance(selection_text, str):
            prompt = prompt.replace(placeholder_key, selection_text)
    

    if len(trends_list) > 0:
        prompt = prompt.replace(f"[[SeedPhrase]]", trends_list[0])

    

    # TODO
    #if len(news_articles) > 0:
    #    for placeholder, key in news_articles[0].items():
    #        prompt = prompt.replace(f"[[{placeholder}]]", trends_list[0])


    # Display the generated prompt
    st.write("Prompt Preview:", prompt)

    st.subheader("Generator")

    user_generator_url = st.text_input("Generator URL", generator_url, key=f"{NEWS_ID_PREFIX}_generator_url")

    user_generator_api_key = st.text_input("Generator API Key", generator_api_key, key=f"{NEWS_ID_PREFIX}_generator_api_key")

    user_generator_api_type = st.selectbox("Generator API Type", generator_api_type, key=f"{NEWS_ID_PREFIX}_generator_api_type")

    user_generator_api_version = st.selectbox("Generator API Version", generator_api_version, key=f"{NEWS_ID_PREFIX}_generator_api_version")

    user_generator_model = st.selectbox("Generator Model", generator_model, key=f"{NEWS_ID_PREFIX}_generator_model")

    recover_original_news = False
    if based_on_real_news:
        st.subheader("News Source config")
        recover_original_news = st.checkbox("Put the retrieve news in the database", value=True )

    if st.button("Generate", key=f"{NEWS_ID_PREFIX}_generate_button"):
        if automated_trends:
            trends_list = get_trends(selected_trends_source)
        if based_on_real_news:
            news_articles = []
            for news_keyword in trends_list:
                news = get_news(news_keyword, user_selections["ISOLanguage"][0])
                if news is not None:
                    news_articles.append(news)
                    st.write({"articleTitle": news.title,
                            "articleDescription": news.description,
                            "articleUrl": news.url,
                            "articleSource": news.convert_url()
                            })
        else:
            news_articles = []

        if recover_original_news:
            for news_article in news_articles:
                news_combination = {
                    "FragmentID": uuid.uuid4().hex,
                    "Content": news_article.description,
                    "Origin": "Human",
                    "HumanOutlet": news_article.convert_url(),
                    "HumanURL": news_article.url,
                    "MachineModel": "",
                    "MachinePrompt": "",
                    "ISOLanguage": user_selections["ISOLanguage"][0],
                    "IsFake": False,
                    "CreationDate": datetime.today()
                }
                save_fragment(news_combination)
        
        
        # Create all combinations of the selected options
        news_articles = articles_to_placeholder(news_articles)
        iter_selections = fix_structure(user_selections)
        iter_selections["SeedPhrase"] = trends_list
        #if based_on_real_news:       
        #    st.write(dict(iter_selections, **{"Articles": news_articles}))
        keys, values = zip(*iter_selections.items())
        combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        if based_on_real_news:       
            combinations = [dict(el[0], **el[1]) for el in itertools.product(combinations, news_articles)]
        
        # Generate and display prompts for each combination
        for i, combination in enumerate(combinations):
            prompt_filled = prompt_template
            for key, value in combination.items():
                prompt_filled = prompt_filled.replace(f"[[{key}]]", value)

            st.write("Using prompt: ", prompt_filled)

            generated_fragment = generate_fragment(
                prompt = prompt_filled,
                base_url = user_generator_url,
                api_key = user_generator_api_key,
                api_type = user_generator_api_type,
                api_version = user_generator_api_version,
                model = user_generator_model
            )
            

            combination["FragmentID"] = uuid.uuid4().hex
            combination["Content"] = generated_fragment
            combination["Origin"] = "Machine"
            combination["MachineModel"] = user_generator_model
            combination["MachinePrompt"] = prompt_filled
            combination["IsFake"] = True
            combination["CreationDate"] = datetime.today()

            #if st.button("Save to DB", key=f"{NEWS_ID_PREFIX}_save_to_db_button_{i}"):
            save_fragment(combination)


            # Add a separator for clarity between prompts
            st.markdown("---")




# UI to input news fragment details
st.title("News Ingestion")

tab_news, tab_generaor, tab_manual = st.tabs(["Automated news import", "Generator", "Manual Data Entry"])

with tab_news:
    news_from_trends_ui()

with tab_generaor:
    automatic_news_generation_ui()

with tab_manual:
    manual_data_entry_ui()
