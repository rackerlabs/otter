SyntaxHighlighter.brushes.Custom = function()
{
    var operators = '{ } [ ] : ,';
    
         
    this.regexList = [
        //Make sure the replacement for the callouts does not get highlighted
        {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g, css: 'removed'},        
        //has a double quote followed by any sequence of characters followed by a double quote followed by colon 
        { regex: /.*\"(.*)\"(\s)*\:/g, css: 'keyword'},
        //opposite the above
        { regex: /[^(.*\".*\"(\s)*\:)]/g, css: 'comments'},

         //has a single quote followed by any sequence of characters followed by a single quote followed by colon 
        { regex: /.*\'.*\'(\s)*\:/g, css: 'keyword'},
        //opposite the above
        { regex: /[^(.*\'.*\'(\s)*\:)]/g, css: 'comments'},
        
        //Handle commas
        //a comma followed by 0 or 1 space
        { regex: /\,(\s)?/g, css: 'string'},  
        
        //Handle the special characters  
        //Any of the braces followed by 1 or 0 space  
        { regex: /(\{|\}|\[|\])(\s)?/g, css: 'plain'},
        //1 or 0 space followed by a } and followed by 1 or 0 space 
        { regex: /(\s)?\}(\s)?/g, css: 'plain'}   

    ];
};
 
SyntaxHighlighter.brushes.Custom.prototype = new SyntaxHighlighter.Highlighter();
SyntaxHighlighter.brushes.Custom.aliases  = ['json', 'JSON'];
